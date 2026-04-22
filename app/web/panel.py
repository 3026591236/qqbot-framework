from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import subprocess
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.card_mode import (
    get_card_mode,
    get_card_mode_label,
    normalize_card_mode,
    set_card_mode,
    set_group_card_mode,
)
from app.config import settings
from app.db import _ensure_column, get_conn
from user_plugins.group_admin import get_auto_recall_seconds

router = APIRouter(prefix="/panel", tags=["panel"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NAPCAT_WEBUI_CONFIG = BASE_DIR / "napcat" / "config" / "webui.json"
PANEL_RUNTIME_DIR = Path(settings.data_dir) / "panel"
PANEL_QRCODE_PATH = PANEL_RUNTIME_DIR / "qrcode.png"
PANEL_SESSION_FILE = PANEL_RUNTIME_DIR / "session_token.txt"
APP_LOG_PATH = Path("/tmp/qqbot-framework-web.log")
NAPCAT_CONTAINER_NAME = "napcat"
NAPCAT_CONTAINER_QRCODE_PATH = "/app/napcat/cache/qrcode.png"


class LoginRequest(BaseModel):
    password: str


class CardModeUpdateRequest(BaseModel):
    mode: str


class GroupCardModeUpdateRequest(BaseModel):
    group_id: int
    mode: str


class AutoRecallUpdateRequest(BaseModel):
    group_id: int
    enabled: bool
    seconds: int = 0


def _require_panel_enabled() -> None:
    if not settings.panel_password:
        raise HTTPException(status_code=503, detail="panel password is not configured")


def _read_session_token() -> str:
    if PANEL_SESSION_FILE.exists():
        return PANEL_SESSION_FILE.read_text(encoding="utf-8").strip()
    return ""


def _write_session_token(token: str) -> None:
    PANEL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PANEL_SESSION_FILE.write_text(token, encoding="utf-8")


def _is_authorized(request: Request) -> bool:
    _require_panel_enabled()
    cookie_token = request.cookies.get("qqbot_panel_session") or ""
    header_token = request.headers.get("x-panel-token") or ""
    provided = cookie_token or header_token
    expected = _read_session_token()
    return bool(expected and provided and hmac.compare_digest(provided, expected))


def _auth_guard(request: Request) -> None:
    if not _is_authorized(request):
        raise HTTPException(status_code=401, detail="unauthorized")


async def _onebot_post(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base = settings.onebot_api_base.rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{base}/{action}", json=payload or {})
        resp.raise_for_status()
        return resp.json()


async def _napcat_login_credential() -> str:
    if not NAPCAT_WEBUI_CONFIG.exists():
        raise RuntimeError(f"NapCat webui config not found: {NAPCAT_WEBUI_CONFIG}")
    data = json.loads(NAPCAT_WEBUI_CONFIG.read_text(encoding="utf-8"))
    token = str(data.get("token") or "").strip()
    if not token:
        raise RuntimeError("NapCat webui token missing")
    token_hash = hashlib.sha256((token + ".napcat").encode("utf-8")).hexdigest()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post("http://127.0.0.1:6099/api/auth/login", json={"hash": token_hash})
        resp.raise_for_status()
        body = resp.json()
        credential = (((body or {}).get("data") or {}).get("Credential")) if isinstance(body, dict) else None
        if not credential:
            raise RuntimeError(f"NapCat webui login failed: {body}")
        return str(credential)


async def _napcat_qqlogin_post(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    credential = await _napcat_login_credential()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"http://127.0.0.1:6099{path}",
            json=payload or {},
            headers={"Authorization": f"Bearer {credential}"},
        )
        resp.raise_for_status()
        return resp.json()


def _ensure_group_admin_settings_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_admin_settings (
                group_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                auto_ban INTEGER NOT NULL DEFAULT 1,
                warn_threshold INTEGER NOT NULL DEFAULT 3,
                auto_ban_duration INTEGER NOT NULL DEFAULT 600,
                auto_recall_enabled INTEGER NOT NULL DEFAULT 0,
                auto_recall_seconds INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        _ensure_column(conn, "group_admin_settings", "auto_recall_enabled", "auto_recall_enabled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "group_admin_settings", "auto_recall_seconds", "auto_recall_seconds INTEGER NOT NULL DEFAULT 0")


def _ensure_group_card_mode_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS group_card_mode_settings (
                group_id INTEGER PRIMARY KEY,
                card_mode TEXT NOT NULL DEFAULT 'text',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )


def _set_auto_recall(group_id: int, enabled: bool, seconds: int) -> dict[str, Any]:
    group_id = int(group_id)
    seconds = max(0, int(seconds or 0))
    _ensure_group_admin_settings_table()
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO group_admin_settings (group_id) VALUES (?)", (group_id,))
        conn.execute(
            "UPDATE group_admin_settings SET auto_recall_enabled=?, auto_recall_seconds=? WHERE group_id=?",
            (1 if enabled else 0, seconds if enabled else 0, group_id),
        )
    return {
        "group_id": group_id,
        "enabled": bool(enabled),
        "seconds": seconds if enabled else 0,
    }


def _get_auto_recall(group_id: int) -> dict[str, Any]:
    seconds = get_auto_recall_seconds(int(group_id))
    return {
        "group_id": int(group_id),
        "enabled": seconds > 0,
        "seconds": seconds,
    }


def _get_group_card_mode(group_id: int) -> dict[str, Any]:
    _ensure_group_card_mode_table()
    with get_conn() as conn:
        row = conn.execute("SELECT card_mode FROM group_card_mode_settings WHERE group_id=?", (int(group_id),)).fetchone()
    mode = normalize_card_mode(row["card_mode"]) if row is not None else ""
    return {
        "group_id": int(group_id),
        "mode": mode or "",
        "effective_mode": get_card_mode(int(group_id)),
        "effective_label": get_card_mode_label(int(group_id)),
        "uses_global_default": row is None,
        "global_default_mode": get_card_mode(),
    }


def _export_qrcode() -> dict[str, Any]:
    PANEL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["docker", "cp", f"{NAPCAT_CONTAINER_NAME}:{NAPCAT_CONTAINER_QRCODE_PATH}", str(PANEL_QRCODE_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )
    stat = PANEL_QRCODE_PATH.stat()
    return {
        "path": str(PANEL_QRCODE_PATH),
        "size": stat.st_size,
        "url": "/panel/qrcode.png",
    }


def _tail_log(lines: int = 200) -> dict[str, Any]:
    path = APP_LOG_PATH
    if not path.exists():
        return {"path": str(path), "exists": False, "content": ""}
    text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = text[-max(1, min(1000, int(lines))):]
    return {"path": str(path), "exists": True, "content": "\n".join(tail)}


@router.get("", response_class=HTMLResponse)
async def panel_index(request: Request) -> str:
    if not _is_authorized(request):
        return """
<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>QQ Bot 面板登录</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0b1020;color:#e5e7eb;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{width:min(420px,92vw);background:#121a2b;border:1px solid #24304a;border-radius:16px;padding:22px;box-shadow:0 8px 24px rgba(0,0,0,.18)}
input,button{width:100%;box-sizing:border-box;border-radius:10px;border:1px solid #334155;background:#0f172a;color:#e5e7eb;padding:12px 14px;margin-top:10px}
button{background:#2563eb;border-color:#2563eb;cursor:pointer}
.err{color:#f87171;min-height:22px;margin-top:8px}
</style></head>
<body><div class="card"><h1>QQ Bot 面板登录</h1><p>这是机器人管理面板，先登录再看。</p><input id="password" type="password" placeholder="输入面板口令" /><button onclick="login()">登录</button><div class="err" id="err"></div></div>
<script>
async function login(){
  const password=document.getElementById('password').value;
  const r=await fetch('/panel/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
  if(r.ok){ location.href='/panel'; return; }
  const data=await r.json().catch(()=>({detail:'登录失败'}));
  document.getElementById('err').innerText=data.detail||'登录失败';
}
</script></body></html>
        """
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QQ Bot 控制面板</title>
  <style>
    body { font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif; margin: 0; background: #0b1020; color: #e5e7eb; }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    .card { background: #121a2b; border: 1px solid #24304a; border-radius: 16px; padding: 18px; box-shadow: 0 8px 24px rgba(0,0,0,.18); }
    h1,h2,h3 { margin-top: 0; }
    .muted { color: #94a3b8; }
    .ok { color: #34d399; }
    .bad { color: #f87171; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
    input, select, button { border-radius: 10px; border: 1px solid #334155; background: #0f172a; color: #e5e7eb; padding: 10px 12px; }
    button { cursor: pointer; background: #2563eb; border-color: #2563eb; }
    button.secondary { background: #1e293b; border-color: #334155; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0f172a; padding: 12px; border-radius: 12px; max-height: 420px; overflow: auto; }
    img { max-width: 100%; border-radius: 12px; background: #fff; }
    .kv { line-height: 1.8; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>QQ Bot 控制面板</h1>
    <p class="muted">当前已支持：登录认证、总览、二维码查看、全局/按群卡片模式、自动撤回、日志查看。</p>
    <div class="grid">
      <div class="card">
        <h2>总览</h2>
        <div id="overview" class="kv muted">加载中...</div>
      </div>
      <div class="card">
        <h2>全局卡片模式</h2>
        <div id="cardMode" class="muted">加载中...</div>
        <div class="row">
          <select id="cardModeSelect"><option value="text">文字</option><option value="image">图片</option></select>
          <button onclick="setCardMode()">保存</button>
        </div>
      </div>
      <div class="card">
        <h2>按群卡片模式</h2>
        <div id="groupCardMode" class="muted">输入群号后查看</div>
        <div class="row">
          <input id="groupCardModeGroupId" placeholder="群号" />
          <select id="groupCardModeSelect"><option value="text">文字</option><option value="image">图片</option></select>
        </div>
        <div class="row">
          <button onclick="loadGroupCardMode()" class="secondary">查询</button>
          <button onclick="setGroupCardMode()">保存</button>
        </div>
      </div>
      <div class="card">
        <h2>群自动撤回</h2>
        <div id="autoRecall" class="muted">输入群号后查看</div>
        <div class="row">
          <input id="groupId" placeholder="群号" />
          <input id="recallSeconds" placeholder="秒数" value="10" />
        </div>
        <div class="row">
          <button onclick="loadAutoRecall()" class="secondary">查询</button>
          <button onclick="enableAutoRecall()">开启/更新</button>
          <button onclick="disableAutoRecall()" class="secondary">关闭</button>
        </div>
      </div>
      <div class="card">
        <h2>登录二维码</h2>
        <div class="row"><button onclick="refreshQrcode()">刷新二维码文件</button></div>
        <div id="qrcodeMeta" class="muted" style="margin-top:10px;">未加载</div>
        <div style="margin-top:12px;"><img id="qrcodeImg" alt="qrcode" /></div>
      </div>
      <div class="card" style="grid-column: 1 / -1;">
        <h2>运行日志</h2>
        <div class="row">
          <input id="logLines" value="200" placeholder="行数" />
          <button onclick="loadLogs()" class="secondary">刷新日志</button>
        </div>
        <pre id="logs">加载中...</pre>
      </div>
      <div class="card" style="grid-column: 1 / -1;">
        <h2>原始状态</h2>
        <pre id="raw">加载中...</pre>
      </div>
    </div>
  </div>
  <script>
    async function jget(url) {
      const r = await fetch(url);
      if (r.status === 401) { location.reload(); throw new Error('unauthorized'); }
      return await r.json();
    }
    async function jpost(url, body) {
      const r = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body || {}) });
      if (r.status === 401) { location.reload(); throw new Error('unauthorized'); }
      return await r.json();
    }
    async function loadStatus() {
      const data = await jget('/panel/api/status');
      document.getElementById('overview').innerHTML = `
        <div>框架健康：<b class="${data.framework_health?.ok ? 'ok' : 'bad'}">${data.framework_health?.ok ? '正常' : '异常'}</b></div>
        <div>OneBot 在线：<b class="${data.onebot_status?.online ? 'ok' : 'bad'}">${data.onebot_status?.online ? '在线' : '离线'}</b></div>
        <div>NapCat 在线：<b class="${data.napcat_login_info?.online ? 'ok' : 'bad'}">${data.napcat_login_info?.online ? '在线' : '离线'}</b></div>
        <div>机器人 QQ：<b>${data.napcat_login_info?.uin || '-'}</b></div>
        <div>昵称：<b>${data.napcat_login_info?.nick || '-'}</b></div>
        <div>当前全局卡片模式：<b>${data.card_mode?.label || '-'}</b></div>`;
      document.getElementById('cardMode').innerText = `当前：${data.card_mode?.mode || '-'} / ${data.card_mode?.label || '-'}`;
      document.getElementById('cardModeSelect').value = data.card_mode?.mode || 'text';
      document.getElementById('raw').innerText = JSON.stringify(data, null, 2);
    }
    async function setCardMode() {
      const mode = document.getElementById('cardModeSelect').value;
      await jpost('/panel/api/card-mode', {mode});
      await loadStatus();
    }
    async function loadGroupCardMode() {
      const gid = document.getElementById('groupCardModeGroupId').value.trim();
      if (!gid) return;
      const data = await jget('/panel/api/group-card-mode?group_id=' + encodeURIComponent(gid));
      document.getElementById('groupCardMode').innerText = `群 ${data.group_id}：显式=${data.mode || '未设置'}，生效=${data.effective_mode}（${data.effective_label}），${data.uses_global_default ? '使用全局默认' : '使用本群设置'}`;
      document.getElementById('groupCardModeSelect').value = data.effective_mode || 'text';
    }
    async function setGroupCardMode() {
      const gid = document.getElementById('groupCardModeGroupId').value.trim();
      const mode = document.getElementById('groupCardModeSelect').value;
      if (!gid) return;
      const data = await jpost('/panel/api/group-card-mode', {group_id: Number(gid), mode});
      document.getElementById('groupCardMode').innerText = `群 ${data.group_id}：已保存为 ${data.mode}`;
    }
    async function loadAutoRecall() {
      const gid = document.getElementById('groupId').value.trim();
      if (!gid) return;
      const data = await jget('/panel/api/group-auto-recall?group_id=' + encodeURIComponent(gid));
      document.getElementById('autoRecall').innerText = `群 ${data.group_id}：${data.enabled ? '已开启' : '已关闭'}，秒数=${data.seconds}`;
      document.getElementById('recallSeconds').value = data.seconds || 10;
    }
    async function enableAutoRecall() {
      const gid = document.getElementById('groupId').value.trim();
      const seconds = Number(document.getElementById('recallSeconds').value || '0');
      if (!gid) return;
      const data = await jpost('/panel/api/group-auto-recall', {group_id: Number(gid), enabled: true, seconds});
      document.getElementById('autoRecall').innerText = `群 ${data.group_id}：已开启，秒数=${data.seconds}`;
    }
    async function disableAutoRecall() {
      const gid = document.getElementById('groupId').value.trim();
      if (!gid) return;
      const data = await jpost('/panel/api/group-auto-recall', {group_id: Number(gid), enabled: false, seconds: 0});
      document.getElementById('autoRecall').innerText = `群 ${data.group_id}：已关闭，秒数=0`;
    }
    async function refreshQrcode() {
      const data = await jpost('/panel/api/qrcode/export', {});
      document.getElementById('qrcodeMeta').innerText = JSON.stringify(data, null, 2);
      if (data.url) document.getElementById('qrcodeImg').src = data.url + '?t=' + Date.now();
    }
    async function loadLogs() {
      const lines = Number(document.getElementById('logLines').value || '200');
      const data = await jget('/panel/api/logs?lines=' + encodeURIComponent(lines));
      document.getElementById('logs').innerText = data.content || '(空)';
    }
    loadStatus(); refreshQrcode(); loadLogs();
  </script>
</body></html>
    """


@router.post("/api/login")
async def panel_login(body: LoginRequest) -> JSONResponse:
    _require_panel_enabled()
    if not hmac.compare_digest(body.password, settings.panel_password):
        raise HTTPException(status_code=401, detail="口令不正确")
    token = secrets.token_urlsafe(32)
    _write_session_token(token)
    response = JSONResponse({"ok": True})
    response.set_cookie("qqbot_panel_session", token, httponly=True, samesite="lax", max_age=86400)
    return response


@router.get("/api/status")
async def panel_status(request: Request) -> dict[str, Any]:
    _auth_guard(request)
    framework_health = {"ok": True, "service": settings.app_name}
    onebot_status: dict[str, Any]
    napcat_login_info: dict[str, Any]
    try:
        onebot_resp = await _onebot_post("get_status")
        onebot_status = (onebot_resp or {}).get("data") or onebot_resp
    except Exception as exc:
        onebot_status = {"ok": False, "error": str(exc), "online": False}
    try:
        napcat_resp = await _napcat_qqlogin_post("/api/QQLogin/GetQQLoginInfo")
        napcat_login_info = (napcat_resp or {}).get("data") or napcat_resp
    except Exception as exc:
        napcat_login_info = {"ok": False, "error": str(exc), "online": False}
    return {
        "framework_health": framework_health,
        "onebot_status": onebot_status,
        "napcat_login_info": napcat_login_info,
        "card_mode": {"mode": get_card_mode(), "label": get_card_mode_label()},
    }


@router.get("/api/card-mode")
async def panel_get_card_mode(request: Request) -> dict[str, Any]:
    _auth_guard(request)
    return {"mode": get_card_mode(), "label": get_card_mode_label()}


@router.post("/api/card-mode")
async def panel_set_card_mode(request: Request, body: CardModeUpdateRequest) -> dict[str, Any]:
    _auth_guard(request)
    mode = set_card_mode(body.mode)
    return {"ok": True, "mode": mode, "label": get_card_mode_label()}


@router.get("/api/group-card-mode")
async def panel_get_group_card_mode(request: Request, group_id: int = Query(...)) -> dict[str, Any]:
    _auth_guard(request)
    return _get_group_card_mode(group_id)


@router.post("/api/group-card-mode")
async def panel_set_group_card_mode_api(request: Request, body: GroupCardModeUpdateRequest) -> dict[str, Any]:
    _auth_guard(request)
    mode = set_group_card_mode(body.group_id, body.mode)
    return {"ok": True, "group_id": int(body.group_id), "mode": mode}


@router.get("/api/group-auto-recall")
async def panel_get_group_auto_recall(request: Request, group_id: int) -> dict[str, Any]:
    _auth_guard(request)
    return _get_auto_recall(group_id)


@router.post("/api/group-auto-recall")
async def panel_set_group_auto_recall(request: Request, body: AutoRecallUpdateRequest) -> dict[str, Any]:
    _auth_guard(request)
    return _set_auto_recall(body.group_id, body.enabled, body.seconds)


@router.get("/api/logs")
async def panel_logs(request: Request, lines: int = 200) -> dict[str, Any]:
    _auth_guard(request)
    return _tail_log(lines)


@router.post("/api/qrcode/export")
async def panel_export_qrcode(request: Request) -> dict[str, Any]:
    _auth_guard(request)
    try:
        return _export_qrcode()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/qrcode.png")
async def panel_qrcode_image(request: Request) -> FileResponse:
    _auth_guard(request)
    if not PANEL_QRCODE_PATH.exists():
        _export_qrcode()
    return FileResponse(PANEL_QRCODE_PATH)
