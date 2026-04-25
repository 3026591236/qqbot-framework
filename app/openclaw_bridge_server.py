from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import websockets
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

OPENCLAW_GATEWAY_WS_URL = os.getenv("OPENCLAW_GATEWAY_WS_URL", "ws://127.0.0.1:18789").rstrip("/")
OPENCLAW_GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
OPENCLAW_BRIDGE_TOKEN = os.getenv("OPENCLAW_BRIDGE_TOKEN", "")
OPENCLAW_TIMEOUT = float(os.getenv("OPENCLAW_TIMEOUT", "120"))
OPENCLAW_DEVICE_PATH = Path(os.getenv("OPENCLAW_DEVICE_PATH", "/root/.openclaw/identity/device.json"))
OPENCLAW_DEVICE_AUTH_PATH = Path(os.getenv("OPENCLAW_DEVICE_AUTH_PATH", "/root/.openclaw/identity/device-auth.json"))

app = FastAPI(title="qqbot-framework openclaw bridge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("openclaw_bridge")


def _load_device_identity() -> dict[str, Any] | None:
    try:
        data = json.loads(OPENCLAW_DEVICE_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read device identity")
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("deviceId") or not data.get("privateKeyPem") or not data.get("publicKeyPem"):
        return None
    return data


def _load_operator_token(device_id: str) -> str:
    if OPENCLAW_GATEWAY_TOKEN:
        return OPENCLAW_GATEWAY_TOKEN
    try:
        data = json.loads(OPENCLAW_DEVICE_AUTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read device auth store")
        return ""
    if not isinstance(data, dict) or data.get("deviceId") != device_id:
        return ""
    tokens = data.get("tokens") or {}
    operator = tokens.get("operator") or {}
    token = operator.get("token")
    return token if isinstance(token, str) else ""


def _device_auth_payload(client_id: str, client_mode: str, role: str, scopes: list[str], nonce: str = "") -> dict[str, Any] | None:
    identity = _load_device_identity()
    if not identity:
        return None
    signed_at = int(time.time() * 1000)
    token = _load_operator_token(identity["deviceId"])
    sign_text = "|".join([
        "v2",
        identity["deviceId"],
        client_id,
        client_mode,
        role,
        ",".join(scopes),
        str(signed_at),
        token,
        nonce,
    ])
    private_key = serialization.load_pem_private_key(identity["privateKeyPem"].encode("utf-8"), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise RuntimeError("device private key is not Ed25519")
    signature = base64.urlsafe_b64encode(private_key.sign(sign_text.encode("utf-8"))).rstrip(b"=").decode("ascii")
    return {
        "id": identity["deviceId"],
        "publicKey": identity["publicKeyPem"],
        "signature": signature,
        "signedAt": signed_at,
        "nonce": nonce,
    }


class SessionSendRequest(BaseModel):
    sessionKey: str
    message: str
    timeoutSeconds: float = 120


class SessionSendResponse(BaseModel):
    ok: bool
    reply: str | dict[str, Any] | list[Any] | None = None
    raw: dict[str, Any] | None = None


def _verify_bridge_token(auth: str | None) -> None:
    if not OPENCLAW_BRIDGE_TOKEN:
        return
    expected = f"Bearer {OPENCLAW_BRIDGE_TOKEN}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def _extract_text_reply(message: Any) -> str | dict[str, Any] | list[Any] | None:
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    text = item["text"].strip()
                    if text:
                        texts.append(text)
            return "\n".join(texts).strip() if texts else None
        return None
    return message if isinstance(message, str) and message.strip() else None


def _message_has_final_text(message: Any) -> bool:
    return _extract_text_reply(message) is not None


async def _gateway_request(ws, method: str, params: dict[str, Any]) -> dict[str, Any]:
    req_id = str(uuid.uuid4())
    req = {"type": "req", "id": req_id, "method": method, "params": params}
    await ws.send(json.dumps(req, ensure_ascii=False))
    while True:
        raw = await ws.recv()
        msg = json.loads(raw)
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "event" and msg.get("event") == "connect.challenge":
            continue
        if msg.get("type") != "res":
            continue
        if msg.get("id") != req_id:
            continue
        if msg.get("ok"):
            return msg.get("payload") or {}
        err = msg.get("error") or {}
        logger.error("gateway error method=%s error=%s", method, err)
        raise HTTPException(status_code=502, detail=err.get("message") or json.dumps(err, ensure_ascii=False))


async def _wait_connect_nonce(ws, timeout_seconds: float = 5.0) -> str:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.5, deadline - asyncio.get_event_loop().time()))
        msg = json.loads(raw)
        if not isinstance(msg, dict):
            continue
        if msg.get("type") != "event":
            continue
        if msg.get("event") != "connect.challenge":
            continue
        payload = msg.get("payload") or {}
        nonce = payload.get("nonce")
        if isinstance(nonce, str) and nonce:
            return nonce
    raise HTTPException(status_code=502, detail="gateway connect challenge nonce timeout")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "gatewayWsUrl": OPENCLAW_GATEWAY_WS_URL,
        "bridgeTokenEnabled": bool(OPENCLAW_BRIDGE_TOKEN),
        "gatewayTokenEnabled": bool(OPENCLAW_GATEWAY_TOKEN),
    }


@app.post("/api/sessions/send", response_model=SessionSendResponse)
async def api_sessions_send(payload: SessionSendRequest, authorization: str | None = Header(default=None)):
    _verify_bridge_token(authorization)
    ws = None
    try:
        ws = await websockets.connect(
            OPENCLAW_GATEWAY_WS_URL,
            open_timeout=OPENCLAW_TIMEOUT,
            close_timeout=5,
            origin="http://127.0.0.1:3001",
        )
        client = {
            "id": "openclaw-control-ui",
            "version": "qqbot-bridge",
            "platform": "linux",
            "mode": "backend",
            "instanceId": "qqbot-framework-openclaw-bridge",
        }
        scopes = ["operator.admin", "operator.read", "operator.write"]
        token = _load_operator_token((_load_device_identity() or {}).get("deviceId", ""))
        connect_params = {
            "minProtocol": 3,
            "maxProtocol": 3,
            "client": client,
            "role": "operator",
            "scopes": scopes,
            "caps": ["tool-events"],
            "auth": {"token": token} if token else {},
        }
        nonce = await _wait_connect_nonce(ws)
        device_auth = _device_auth_payload(client_id=client["id"], client_mode=client["mode"], role="operator", scopes=scopes, nonce=nonce)
        if device_auth:
            connect_params["device"] = device_auth
        await _gateway_request(ws, "connect", connect_params)
        await _gateway_request(ws, "sessions.subscribe", {"sessionKey": payload.sessionKey})
        history_before = await _gateway_request(ws, "chat.history", {
            "sessionKey": payload.sessionKey,
            "limit": 1,
        })
        before_messages = history_before.get("messages") if isinstance(history_before, dict) else None
        baseline_seq = 0
        if isinstance(before_messages, list) and before_messages:
            last_message = before_messages[-1]
            if isinstance(last_message, dict):
                openclaw_meta = last_message.get("__openclaw") or {}
                seq = openclaw_meta.get("seq")
                if isinstance(seq, int):
                    baseline_seq = seq

        await _gateway_request(ws, "chat.send", {
            "sessionKey": payload.sessionKey,
            "message": payload.message,
            "deliver": False,
            "idempotencyKey": str(uuid.uuid4()),
        })
        deadline = asyncio.get_event_loop().time() + payload.timeoutSeconds
        final_message: dict[str, Any] | None = None
        final_run_id: str | None = None
        next_history_check_at = asyncio.get_event_loop().time() + 4.0
        history_check_interval = 4.0
        while asyncio.get_event_loop().time() < deadline:
            remaining = max(0.1, deadline - asyncio.get_event_loop().time())
            now = asyncio.get_event_loop().time()
            wait_timeout = min(2.5, remaining, max(0.1, next_history_check_at - now))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=wait_timeout)
                msg = json.loads(raw)
            except asyncio.TimeoutError:
                msg = None

            if isinstance(msg, dict) and msg.get("type") == "event":
                event_name = msg.get("event")
                event_payload = msg.get("payload") or {}
                if event_payload.get("sessionKey") == payload.sessionKey:
                    if event_name == "session.message":
                        message = event_payload.get("message")
                        if isinstance(message, dict) and message.get("role") == "assistant":
                            openclaw_meta = message.get("__openclaw") or {}
                            seq = openclaw_meta.get("seq")
                            if isinstance(seq, int) and seq > baseline_seq and _message_has_final_text(message):
                                final_message = message
                                break
                    elif event_name == "chat.final":
                        message = event_payload.get("message") or event_payload
                        if isinstance(message, dict):
                            openclaw_meta = message.get("__openclaw") or {}
                            seq = openclaw_meta.get("seq")
                            if (not isinstance(seq, int) or seq > baseline_seq) and _message_has_final_text(message):
                                final_message = message
                                break
                    elif event_name == "chat" and event_payload.get("state") == "final":
                        final_run_id = event_payload.get("runId") if isinstance(event_payload.get("runId"), str) else None
                        next_history_check_at = asyncio.get_event_loop().time()

            now = asyncio.get_event_loop().time()
            if final_message is None and now >= next_history_check_at:
                history = await _gateway_request(ws, "chat.history", {
                    "sessionKey": payload.sessionKey,
                    "limit": 10,
                })
                items = None
                if isinstance(history, dict):
                    items = history.get("messages") or history.get("items")
                if isinstance(items, list):
                    for item in reversed(items):
                        if not isinstance(item, dict):
                            continue
                        if item.get("role") != "assistant":
                            continue
                        openclaw_meta = item.get("__openclaw") or {}
                        seq = openclaw_meta.get("seq")
                        if not isinstance(seq, int) or seq <= baseline_seq:
                            continue
                        if final_run_id and item.get("runId") not in (final_run_id, None):
                            continue
                        if not _message_has_final_text(item):
                            continue
                        final_message = item
                        break
                next_history_check_at = now + history_check_interval
                if final_message is not None:
                    break

        if final_message is None:
            raise HTTPException(status_code=504, detail="wait chat final timeout")

        reply = _extract_text_reply(final_message)
        if reply is None:
            raise HTTPException(status_code=504, detail="wait final text reply timeout")
        return SessionSendResponse(ok=True, reply=reply, raw={"message": final_message})
    except HTTPException as exc:
        logger.error("bridge http error detail=%s", exc.detail)
        raise
    except Exception as exc:
        logger.exception("bridge unexpected error")
        raise HTTPException(status_code=502, detail=f"openclaw gateway request failed: {exc}")
    finally:
        if ws is not None:
            await ws.close()
