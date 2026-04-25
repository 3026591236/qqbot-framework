from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

OPENCLAW_BASE_URL = os.getenv("OPENCLAW_BASE_URL", "http://127.0.0.1:3001").rstrip("/")
OPENCLAW_API_KEY = os.getenv("OPENCLAW_API_KEY", "")
OPENCLAW_BRIDGE_TOKEN = os.getenv("OPENCLAW_BRIDGE_TOKEN", "")
OPENCLAW_TIMEOUT = float(os.getenv("OPENCLAW_TIMEOUT", "120"))

app = FastAPI(title="qqbot-framework openclaw bridge")


class SessionSendRequest(BaseModel):
    sessionKey: str
    message: str
    timeoutSeconds: float = 120


class SessionSendResponse(BaseModel):
    ok: bool
    reply: str | dict[str, Any] | list[Any] | None = None
    raw: dict[str, Any] | None = None


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_API_KEY:
        headers["Authorization"] = f"Bearer {OPENCLAW_API_KEY}"
    return headers


def _verify_bridge_token(auth: str | None) -> None:
    if not OPENCLAW_BRIDGE_TOKEN:
        return
    expected = f"Bearer {OPENCLAW_BRIDGE_TOKEN}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "openclawBaseUrl": OPENCLAW_BASE_URL,
        "bridgeTokenEnabled": bool(OPENCLAW_BRIDGE_TOKEN),
    }


@app.post("/api/sessions/send", response_model=SessionSendResponse)
async def api_sessions_send(payload: SessionSendRequest, authorization: str | None = Header(default=None)):
    _verify_bridge_token(authorization)
    url = f"{OPENCLAW_BASE_URL}/api/sessions/send"
    body = {
        "sessionKey": payload.sessionKey,
        "message": payload.message,
        "timeoutSeconds": payload.timeoutSeconds,
    }
    try:
        async with httpx.AsyncClient(timeout=OPENCLAW_TIMEOUT) as client:
            resp = await client.post(url, json=body, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"openclaw status error: {exc.response.text[:500]}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"openclaw request failed: {exc}")

    reply = None
    if isinstance(data, dict):
        reply = data.get("reply") or data.get("message") or data.get("result")
        if reply is None and "assistant" in data:
            reply = data.get("assistant")
        if reply is None:
            reply = data

    return SessionSendResponse(ok=True, reply=reply, raw=data if isinstance(data, dict) else {"raw": data})
