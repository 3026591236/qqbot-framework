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

from collections.abc import Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import websockets
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import httpx

OPENCLAW_GATEWAY_WS_URL = os.getenv("OPENCLAW_GATEWAY_WS_URL", "ws://127.0.0.1:18789").rstrip("/")
OPENCLAW_GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
OPENCLAW_BRIDGE_TOKEN = os.getenv("OPENCLAW_BRIDGE_TOKEN", "")
OPENCLAW_TIMEOUT = float(os.getenv("OPENCLAW_TIMEOUT", "120"))
OPENCLAW_DEVICE_PATH = Path(os.getenv("OPENCLAW_DEVICE_PATH", "/root/.openclaw/identity/device.json"))
OPENCLAW_DEVICE_AUTH_PATH = Path(os.getenv("OPENCLAW_DEVICE_AUTH_PATH", "/root/.openclaw/identity/device-auth.json"))

app = FastAPI(title="qqbot-framework openclaw bridge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("openclaw_bridge")

_WATCHES: dict[str, dict[str, Any]] = {}
_WATCH_LOCK = asyncio.Lock()


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


class ImageAttachment(BaseModel):
    url: str
    mimeType: str | None = None


class SessionSendRequest(BaseModel):
    sessionKey: str
    message: str
    timeoutSeconds: float = 120
    attachments: list[ImageAttachment] | None = None


class SessionSendResponse(BaseModel):
    ok: bool
    reply: str | dict[str, Any] | list[Any] | None = None
    imageUrls: list[str] | None = None
    raw: dict[str, Any] | None = None


class WatchStartRequest(BaseModel):
    sessionKey: str
    timeoutSeconds: float = 600


class WatchStartResponse(BaseModel):
    ok: bool
    watchId: str
    state: str


class WatchPollResponse(BaseModel):
    ok: bool
    watchId: str
    state: str
    done: bool
    waitingForUser: bool = False
    reply: str | dict[str, Any] | list[Any] | None = None
    imageUrls: list[str] | None = None
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


def _extract_image_urls_from_message(message: Any) -> list[str]:
    urls: list[str] = []
    if not isinstance(message, dict):
        return urls
    content = message.get("content")
    if not isinstance(content, list):
        return urls
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "image_url":
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                url = image_url.get("url")
                if isinstance(url, str) and url.strip():
                    urls.append(url.strip())
        elif item.get("type") == "image":
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                urls.append(url.strip())
    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def _message_has_final_text(message: Any) -> bool:
    return _extract_text_reply(message) is not None


def _message_has_final_payload(message: Any) -> bool:
    return _extract_text_reply(message) is not None or bool(_extract_image_urls_from_message(message))


def _reply_waiting_for_user(reply: Any) -> bool:
    if not isinstance(reply, str):
        return False
    text = reply.strip()
    if not text:
        return False
    patterns = [
        "请输入", "请提供", "请发送", "请发我", "请把", "把.*发我", "发我", "告诉我", "回复我", "把验证码", "验证码",
        "需要你", "还需要", "缺少", "补充", "上传", "图片发来", "发图片", "等你", "我再继续", "继续帮你",
        "确认", "选择", "要不要", "是否", "几位", "哪一个", "哪个", "什么", "多少", "怎么填"
    ]
    return any(p in text for p in patterns)


async def _download_attachments(attachments: list[ImageAttachment] | None) -> list[dict[str, str]]:
    if not attachments:
        return []
    results: list[dict[str, str]] = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for item in attachments:
            url = (item.url or "").strip()
            if not url:
                continue
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as exc:
                logger.exception("attachment download failed url=%s", url)
                continue
            mime_type = item.mimeType or resp.headers.get("content-type", "image/png").split(";")[0].strip() or "image/png"
            logger.info("attachment downloaded url=%s mime=%s size=%s", url, mime_type, len(resp.content))
            results.append({
                "type": "image",
                "mimeType": mime_type,
                "content": base64.b64encode(resp.content).decode("ascii"),
            })
    return results


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


async def _connect_gateway():
    ws = await websockets.connect(
        OPENCLAW_GATEWAY_WS_URL,
        open_timeout=OPENCLAW_TIMEOUT,
        close_timeout=5,
        max_size=8 * 1024 * 1024,
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
    return ws


async def _wait_for_assistant_reply(ws, session_key: str, timeout_seconds: float, baseline_seq: int = 0) -> dict[str, Any]:
    await _gateway_request(ws, "sessions.subscribe", {"sessionKey": session_key})
    deadline = asyncio.get_event_loop().time() + timeout_seconds
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
            if event_payload.get("sessionKey") == session_key:
                if event_name == "session.message":
                    message = event_payload.get("message")
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        openclaw_meta = message.get("__openclaw") or {}
                        seq = openclaw_meta.get("seq")
                        if isinstance(seq, int) and seq > baseline_seq and _message_has_final_payload(message):
                            final_message = message
                            break
                elif event_name == "chat.final":
                    message = event_payload.get("message") or event_payload
                    if isinstance(message, dict):
                        openclaw_meta = message.get("__openclaw") or {}
                        seq = openclaw_meta.get("seq")
                        if (not isinstance(seq, int) or seq > baseline_seq) and _message_has_final_payload(message):
                            final_message = message
                            break
                elif event_name == "chat" and event_payload.get("state") == "final":
                    final_run_id = event_payload.get("runId") if isinstance(event_payload.get("runId"), str) else None
                    next_history_check_at = asyncio.get_event_loop().time()

        now = asyncio.get_event_loop().time()
        if final_message is None and now >= next_history_check_at:
            history = await _gateway_request(ws, "chat.history", {
                "sessionKey": session_key,
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
                    if not _message_has_final_payload(item):
                        continue
                    final_message = item
                    break
            next_history_check_at = now + history_check_interval
            if final_message is not None:
                break

    if final_message is None:
        history = await _gateway_request(ws, "chat.history", {
            "sessionKey": session_key,
            "limit": 20,
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
                if _message_has_final_payload(item):
                    final_message = item
                    break
    if final_message is None:
        raise HTTPException(status_code=504, detail="wait chat final timeout")
    return final_message


async def _record_watch_update(watch_id: str, *, state: str, message: dict[str, Any] | None = None, error: str | None = None) -> None:
    async with _WATCH_LOCK:
        watch = _WATCHES.get(watch_id)
        if not watch:
            return
        watch["state"] = state
        watch["updatedAt"] = time.time()
        if message is not None:
            watch["message"] = message
            reply = _extract_text_reply(message)
            watch["reply"] = reply
            watch["imageUrls"] = _extract_image_urls_from_message(message) or None
            watch["waitingForUser"] = _reply_waiting_for_user(reply)
            if watch["waitingForUser"]:
                watch["state"] = "waiting_for_user"
            watch["raw"] = {"message": message}
        if error is not None:
            watch["error"] = error


async def _watch_session_reply(watch_id: str, session_key: str, timeout_seconds: float, baseline_seq: int) -> None:
    ws = None
    try:
        await _record_watch_update(watch_id, state="watching")
        ws = await _connect_gateway()
        message = await _wait_for_assistant_reply(ws, session_key, timeout_seconds, baseline_seq=baseline_seq)
        await _record_watch_update(watch_id, state="done", message=message)
    except Exception as exc:
        logger.exception("watch failed watchId=%s session=%s", watch_id, session_key)
        await _record_watch_update(watch_id, state="failed", error=str(exc))
    finally:
        if ws is not None:
            await ws.close()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "gatewayWsUrl": OPENCLAW_GATEWAY_WS_URL,
        "bridgeTokenEnabled": bool(OPENCLAW_BRIDGE_TOKEN),
        "gatewayTokenEnabled": bool(OPENCLAW_GATEWAY_TOKEN),
        "watchCount": len(_WATCHES),
    }


@app.post("/api/sessions/send", response_model=SessionSendResponse)
async def api_sessions_send(payload: SessionSendRequest, authorization: str | None = Header(default=None)):
    _verify_bridge_token(authorization)
    ws = None
    try:
        ws = await _connect_gateway()
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

        attachment_payloads = await _download_attachments(payload.attachments)
        chat_send_params = {
            "sessionKey": payload.sessionKey,
            "message": payload.message,
            "deliver": False,
            "idempotencyKey": str(uuid.uuid4()),
        }
        if attachment_payloads:
            chat_send_params["attachments"] = attachment_payloads
        logger.info("chat.send session=%s message_len=%s attachments=%s", payload.sessionKey, len(payload.message or ""), len(attachment_payloads))
        await _gateway_request(ws, "chat.send", chat_send_params)
        final_message = await _wait_for_assistant_reply(ws, payload.sessionKey, payload.timeoutSeconds, baseline_seq=baseline_seq)

        reply = _extract_text_reply(final_message)
        image_urls = _extract_image_urls_from_message(final_message)
        if reply is None and not image_urls:
            raise HTTPException(status_code=504, detail="wait final text reply timeout")
        return SessionSendResponse(ok=True, reply=reply, imageUrls=image_urls or None, raw={"message": final_message})
    except HTTPException as exc:
        logger.error("bridge http error detail=%s", exc.detail)
        raise
    except Exception as exc:
        logger.exception("bridge unexpected error")
        raise HTTPException(status_code=502, detail=f"openclaw gateway request failed: {exc}")
    finally:
        if ws is not None:
            await ws.close()


@app.post("/api/watch/start", response_model=WatchStartResponse)
async def api_watch_start(payload: WatchStartRequest, authorization: str | None = Header(default=None)):
    _verify_bridge_token(authorization)
    watch_id = str(uuid.uuid4())
    ws = None
    try:
        ws = await _connect_gateway()
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
        async with _WATCH_LOCK:
            _WATCHES[watch_id] = {
                "watchId": watch_id,
                "sessionKey": payload.sessionKey,
                "state": "starting",
                "createdAt": time.time(),
                "updatedAt": time.time(),
                "baselineSeq": baseline_seq,
                "reply": None,
                "imageUrls": None,
                "waitingForUser": False,
                "raw": None,
                "error": None,
            }
        asyncio.create_task(_watch_session_reply(watch_id, payload.sessionKey, payload.timeoutSeconds, baseline_seq))
        return WatchStartResponse(ok=True, watchId=watch_id, state="starting")
    finally:
        if ws is not None:
            await ws.close()


@app.get("/api/watch/{watch_id}", response_model=WatchPollResponse)
async def api_watch_poll(watch_id: str, authorization: str | None = Header(default=None)):
    _verify_bridge_token(authorization)
    async with _WATCH_LOCK:
        watch = _WATCHES.get(watch_id)
        if not watch:
            raise HTTPException(status_code=404, detail="watch not found")
        state = str(watch.get("state") or "unknown")
        done = state in {"done", "failed", "cancelled", "timeout", "waiting_for_user"}
        reply = watch.get("reply")
        if state == "failed" and not reply:
            reply = watch.get("error")
        return WatchPollResponse(
            ok=True,
            watchId=watch_id,
            state=state,
            done=done,
            waitingForUser=bool(watch.get("waitingForUser")),
            reply=reply,
            imageUrls=watch.get("imageUrls"),
            raw=watch.get("raw"),
        )
