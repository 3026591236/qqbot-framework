from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import subprocess
import time
import zipfile
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
from app.plugin_market import get_market_plugin, list_market_plugins
from app.plugin_registry import list_plugins as list_plugin_registry
from app.plugin_registry import set_enabled as set_plugin_enabled
from user_plugins.group_admin import get_auto_recall_seconds

router = APIRouter(prefix="/panel", tags=["panel"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NAPCAT_WEBUI_CONFIG = BASE_DIR / "napcat" / "config" / "webui.json"
PANEL_RUNTIME_DIR = Path(settings.data_dir) / "panel"
PANEL_QRCODE_PATH = PANEL_RUNTIME_DIR / "qrcode.png"
PANEL_SESSION_FILE = PANEL_RUNTIME_DIR / "session_token.txt"
PANEL_LOGIN_STATE_FILE = PANEL_RUNTIME_DIR / "login_state.json"
PANEL_BACKUP_DIR = PANEL_RUNTIME_DIR / "backups"
MARKET_INSTALLED_PATH = Path(settings.data_dir) / "market_installed.json"
MARKET_PLUGIN_PREFIX = "market_"
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


class SendMessageRequest(BaseModel):
    # kind: group | private
    kind: str
    target_id: int
    text: str = ""
    image_url: str = ""


class PanelPluginToggleRequest(BaseModel):
    name: str
    enabled: bool


class SelfcheckRequest(BaseModel):
    # How many log lines to include
    log_lines: int = 120


class BackupRequest(BaseModel):
    include_sqlite: bool = True


class MarketInstallRequest(BaseModel):
    name: str


class MarketRemoveRequest(BaseModel):
    name: str


class RestartRequest(BaseModel):
    confirm: bool = False


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


def _client_ip(request: Request) -> str:
    # best-effort; relies on infra to pass real client IP (e.g. proxy headers)
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    return request.client.host if request.client else ""


def _is_authorized(request: Request) -> bool:
    _require_panel_enabled()

    # Optional IP allowlist gate
    allow_ips = getattr(settings, "panel_allow_ips", ()) or ()
    if allow_ips:
        ip = _client_ip(request)
        if ip not in set(allow_ips):
            return False

    cookie_token = request.cookies.get("qqbot_panel_session") or ""
    header_token = request.headers.get("x-panel-token") or ""
    provided = cookie_token or header_token
    expected = _read_session_token()
    return bool(expected and provided and hmac.compare_digest(provided, expected))


def _auth_guard(request: Request) -> None:
    if not _is_authorized(request):
        # If IP allowlist is enabled, distinguish to help ops.
        allow_ips = getattr(settings, "panel_allow_ips", ()) or ()
        if allow_ips:
            raise HTTPException(status_code=403, detail="forbidden")
        raise HTTPException(status_code=401, detail="unauthorized")


def _read_login_state() -> dict[str, Any]:
    if PANEL_LOGIN_STATE_FILE.exists():
        try:
            return json.loads(PANEL_LOGIN_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_login_state(state: dict[str, Any]) -> None:
    PANEL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PANEL_LOGIN_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _mark_login_action(action: str, note: str = "") -> None:
    state = _read_login_state()
    state.update(
        {
            "last_action": action,
            "last_action_at": int(time.time()),
            "last_note": note,
        }
    )
    _write_login_state(state)


def _tail_container_logs(container: str, lines: int = 200) -> str:
    lines = max(1, min(2000, int(lines)))
    try:
        r = subprocess.run(
            ["docker", "logs", "--tail", str(lines), container],
            check=True,
            capture_output=True,
            text=True,
        )
        return (r.stdout or "")[-200_000:]
    except Exception as exc:
        return f"(failed to read docker logs: {exc})"


def _backup_runtime(include_sqlite: bool = True) -> dict[str, Any]:
    """Create a downloadable zip snapshot of runtime config/data.

    IMPORTANT: This may include sensitive data (.env, tokens, sqlite). Keep it authenticated.
    """
    PANEL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = PANEL_BACKUP_DIR / f"qqbot_backup_{ts}.zip"

    base = BASE_DIR
    paths: list[tuple[Path, str]] = []

    # Core runtime config
    for rel in [
        Path(".env"),
        Path("data") / "plugins.json",
        Path("data") / "group_card_mode.json",
        Path("data") / "market_installed.json",
        Path("data") / "qqbot.sqlite3",
        Path("napcat") / "config",
    ]:
        p = base / rel
        if not p.exists():
            continue
        if p.name == "qqbot.sqlite3" and not include_sqlite:
            continue
        paths.append((p, str(rel)))

    def add_path(p: Path, arc: str) -> None:
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    rel_arc = f"{arc}/{child.relative_to(p).as_posix()}"
                    z.write(child, rel_arc)
        else:
            z.write(p, arc)

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p, arc in paths:
            add_path(p, arc)

    return {"ok": True, "path": str(out), "url": f"/panel/api/backup/download?file={out.name}"}


def _load_market_installed() -> dict[str, Any]:
    if not MARKET_INSTALLED_PATH.exists():
        return {"installed": {}}
    try:
        return json.loads(MARKET_INSTALLED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"installed": {}}


def _save_market_installed(data: dict[str, Any]) -> None:
    MARKET_INSTALLED_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKET_INSTALLED_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_market_filename(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)
    return f"{MARKET_PLUGIN_PREFIX}{safe}.py"


async def _onebot_post(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base = settings.onebot_api_base.rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{base}/{action}", json=payload or {})
        resp.raise_for_status()
        return resp.json()


async def _send_via_onebot(kind: str, target_id: int, text: str = "", image_url: str = "") -> dict[str, Any]:
    kind = (kind or "").strip().lower()
    if kind not in {"group", "private"}:
        raise HTTPException(status_code=400, detail="kind must be group|private")
    if not target_id:
        raise HTTPException(status_code=400, detail="target_id required")

    # Build OneBot v11 message segments
    message: list[dict[str, Any]] = []
    if text:
        message.append({"type": "text", "data": {"text": str(text)}})
    if image_url:
        message.append({"type": "image", "data": {"file": str(image_url)}})
    if not message:
        raise HTTPException(status_code=400, detail="empty message")

    action = "send_group_msg" if kind == "group" else "send_private_msg"
    payload: dict[str, Any] = {"message": message}
    if kind == "group":
        payload["group_id"] = int(target_id)
    else:
        payload["user_id"] = int(target_id)
    return await _onebot_post(action, payload)


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
    """Export the current NapCat QRCode PNG from the container.

    Notes:
    - This is used by the panel for login/re-login.
    - We prefer exporting on-demand (and even before each image request) because
      QR codes expire quickly; a cached file is often already stale when the user opens it.
    """
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


def _get_napcat_webui_token() -> str:
    if not NAPCAT_WEBUI_CONFIG.exists():
        return ""
    try:
        data = json.loads(NAPCAT_WEBUI_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(data.get("token") or "").strip()


def _napcat_webui_url_for_request(request: Request) -> str:
    token = _get_napcat_webui_token()
    if not token:
        return ""
    scheme = request.url.scheme or "http"
    host = request.url.hostname or "127.0.0.1"
    return f"{scheme}://{host}:6099/webui?token={token}"


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
    .layout { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
    .sidebar { background: #0d1426; border-right: 1px solid #24304a; padding: 18px 14px; position: sticky; top: 0; height: 100vh; box-sizing: border-box; }
    .brand { padding: 10px 10px 16px; border-bottom: 1px solid #24304a; margin-bottom: 12px; }
    .brand .title { font-size: 18px; font-weight: 700; }
    .brand .sub { font-size: 12px; margin-top: 2px; }
    .menu a { display: block; padding: 10px 12px; border-radius: 12px; color: #e5e7eb; text-decoration: none; margin: 6px 0; border: 1px solid transparent; font-size: 14px; }
    .menu a:hover { background: #121a2b; border-color: #24304a; }
    .menu a.active { background: #1a2a52; border-color: #2b3a64; }
    .foot { padding: 10px 12px; font-size: 12px; border-top: 1px solid #24304a; margin-top: 14px; }
    .content { padding: 22px; }
    .topbar { max-width: 1200px; margin: 0 auto 16px; }
    .grid { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    .section { display: none; }
    .section.active { display: block; }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .sidebar { position: relative; height: auto; }
    }
    .card { background: #121a2b; border: 1px solid #24304a; border-radius: 16px; padding: 18px; box-shadow: 0 8px 24px rgba(0,0,0,.18); }
    h1,h2,h3 { margin-top: 0; }
    .muted { color: #94a3b8; }
    .ok { color: #34d399; }
    .bad { color: #f87171; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; align-items: center; }
    input, select, button { border-radius: 10px; border: 1px solid #334155; background: #0f172a; color: #e5e7eb; padding: 10px 12px; }
    button { cursor: pointer; background: #2563eb; border-color: #2563eb; }
    button.secondary { background: #1e293b; border-color: #334155; }
    button.danger { background: #991b1b; border-color: #991b1b; }
    .badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px; font-size: 12px; border: 1px solid #24304a; background: #0f172a; }
    .badge.ok { color: #34d399; border-color: rgba(52,211,153,.35); }
    .badge.bad { color: #f87171; border-color: rgba(248,113,113,.35); }
    .list { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
    .item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; border-radius: 14px; border: 1px solid #24304a; background: #0f172a; }
    .item .meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
    .item .meta .name { font-weight: 700; }
    .item .meta .desc { font-size: 12px; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 52vw; }
    .item .actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0f172a; padding: 12px; border-radius: 12px; max-height: 420px; overflow: auto; font-size: 12px; line-height: 1.45; }
    img { max-width: 100%; border-radius: 12px; background: #fff; }
    .kv { line-height: 1.8; }
    details { border: 1px dashed #24304a; border-radius: 14px; padding: 10px 12px; margin-top: 10px; }
    details > summary { cursor: pointer; color: #cbd5e1; }
    @media (max-width: 520px) {
      .content { padding: 14px; }
      .grid { grid-template-columns: 1fr; }
      .item { flex-direction: column; align-items: flex-start; }
      .item .actions { width: 100%; justify-content: flex-start; }
      .item .meta .desc { max-width: 78vw; }
      button { width: 100%; }
      input, select { width: 100%; }
    }
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="title">QQ Bot</div>
        <div class="sub muted">控制面板</div>
      </div>
      <nav class="menu">
        <a href="#dashboard" id="m-dashboard">总览</a>
        <a href="#login" id="m-login">登录/二维码</a>
        <a href="#ops" id="m-ops">运维/排障</a>
        <a href="#plugins" id="m-plugins">插件管理</a>
        <a href="#market" id="m-market">插件商店</a>
        <a href="#backup" id="m-backup">备份</a>
        <a href="#raw" id="m-raw">原始状态</a>
      </nav>
      <div class="foot muted" id="sideStatus">加载中...</div>
    </aside>

    <main class="content">
      <div class="topbar">
        <h1>QQ Bot 控制面板</h1>
        <p class="muted">左侧菜单切换功能区；登录二维码建议使用 NapCat WebUI 实时二维码。</p>
      </div>

      <section class="section" id="sec-dashboard">
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
        </div>
      </section>

      <section class="section" id="sec-login">
        <div class="grid">
          <div class="card" style="grid-column: 1 / -1;">
            <h2>登录二维码</h2>
            <p class="muted">提示：二维码过期很快，优先点总览里的「NapCat WebUI：打开实时二维码」。</p>
            <div class="row"><button onclick="refreshQrcode()">刷新二维码文件</button></div>
            <div id="qrcodeMeta" class="muted" style="margin-top:10px;">未加载</div>
            <div style="margin-top:12px;"><img id="qrcodeImg" alt="qrcode" /></div>
          </div>
        </div>
      </section>

      <section class="section" id="sec-ops">
        <div class="grid">
          <div class="card" style="grid-column: 1 / -1;">
            <h2>发送消息（OneBot）</h2>
            <p class="muted">用于排障：从面板直接发群/私聊消息，验证 OneBot 能否发送图片/文本。</p>
            <div class="row">
              <select id="sendKind">
                <option value="group">群</option>
                <option value="private">私聊</option>
              </select>
              <input id="sendTarget" placeholder="群号/QQ号" />
              <input id="sendText" placeholder="文本（可选）" style="flex:1; min-width:260px;" />
            </div>
            <div class="row">
              <input id="sendImageUrl" placeholder="图片URL（可选，例如 http://host.docker.internal:9000/... 或 https://...）" style="flex:1; min-width:260px;" />
              <button onclick="sendMsg()">发送</button>
            </div>
            <pre id="sendResult" class="muted">未发送</pre>
          </div>

          <div class="card" style="grid-column: 1 / -1;">
            <h2>一键自检（更适合人看）</h2>
            <p class="muted">把 OneBot/NapCat 的关键状态汇总成“结论 + 原因”。下面还有可展开的原始数据。</p>
            <div class="row">
              <input id="selfcheckLines" value="120" placeholder="日志行数" />
              <button onclick="runSelfcheck()">运行自检</button>
            </div>
            <div class="row" id="selfcheckBadges" style="margin-top: 10px;"></div>
            <div id="selfcheckSummary" class="muted" style="margin-top: 8px;">未运行</div>
            <details>
              <summary>查看原始自检数据（JSON）</summary>
              <pre id="selfcheck" class="muted">未运行</pre>
            </details>
          </div>

          <div class="card" style="grid-column: 1 / -1;">
            <h2>运行日志</h2>
            <div class="row">
              <input id="logLines" value="200" placeholder="行数" />
              <button onclick="loadLogs()" class="secondary">刷新日志</button>
            </div>
            <pre id="logs">加载中...</pre>
          </div>
        </div>
      </section>

      <section class="section" id="sec-plugins">
        <div class="grid">
          <div class="card" style="grid-column: 1 / -1;">
            <h2>插件管理（可点选）</h2>
            <p class="muted">这是“框架内置/本地插件”的启用开关。切换后需要重启框架生效。</p>
            <div class="row">
              <button class="secondary" onclick="loadPlugins()">刷新插件列表</button>
            </div>
            <div id="pluginsList" class="list">加载中...</div>
            <div class="row">
              <button onclick="restartFromPlugins()">一键重启框架（让插件开关生效）</button>
            </div>
            <div id="pluginResult" class="muted" style="margin-top:10px;">未操作</div>
            <details>
              <summary>查看原始插件注册表（JSON）</summary>
              <pre id="plugins" class="muted">加载中...</pre>
            </details>
          </div>
        </div>
      </section>

      <section class="section" id="sec-market">
        <div class="grid">
          <div class="card" style="grid-column: 1 / -1;">
            <h2>插件商店</h2>
            <p class="muted">从配置的 QQBOT_MARKET_URL 拉取 market.json。安装/卸载后需要重启框架进程才生效。</p>
            <div class="row">
              <button class="secondary" onclick="loadMarket()">刷新商店列表</button>
            </div>
            <pre id="marketList" class="muted">加载中...</pre>
            <div class="row">
              <input id="marketName" placeholder="插件名（name）" />
              <button onclick="marketInstall()">安装</button>
              <button class="secondary" onclick="marketRemove()">卸载</button>
            </div>
            <pre id="marketResult" class="muted">未操作</pre>
          </div>
          <div class="card" style="grid-column: 1 / -1;">
            <h2>已安装（商店）</h2>
            <div class="row">
              <button class="secondary" onclick="loadMarketInstalled()">刷新已安装</button>
              <button onclick="restartApp()">一键重启框架（生效安装/卸载）</button>
            </div>
            <pre id="marketInstalled" class="muted">加载中...</pre>
          </div>
        </div>
      </section>

      <section class="section" id="sec-backup">
        <div class="grid">
          <div class="card" style="grid-column: 1 / -1;">
            <h2>备份下载</h2>
            <p class="muted">生成一个 zip 备份（可能包含敏感信息：.env / napcat config / sqlite）。仅在你信任的环境下载保存。</p>
            <div class="row">
              <select id="backupIncludeSqlite"><option value="true">包含数据库 sqlite</option><option value="false">不包含数据库</option></select>
              <button onclick="createBackup()">生成备份</button>
            </div>
            <pre id="backup" class="muted">未生成</pre>
          </div>
        </div>
      </section>

      <section class="section" id="sec-raw">
        <div class="grid">
          <div class="card" style="grid-column: 1 / -1;">
            <h2>原始状态</h2>
            <pre id="raw">加载中...</pre>
          </div>
        </div>
      </section>
    </main>
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
      const webuiUrl = data.napcat_webui_url || '';
      const onebotOnline = !!data.onebot_status?.online;
      const napcatOnline = !!data.napcat_login_info?.online;
      document.getElementById('overview').innerHTML = `
        <div>框架健康：<b class="${data.framework_health?.ok ? 'ok' : 'bad'}">${data.framework_health?.ok ? '正常' : '异常'}</b></div>
        <div>OneBot 在线：<b class="${onebotOnline ? 'ok' : 'bad'}">${onebotOnline ? '在线' : '离线'}</b></div>
        <div>NapCat 在线：<b class="${napcatOnline ? 'ok' : 'bad'}">${napcatOnline ? '在线' : '离线'}</b></div>
        <div>机器人 QQ：<b>${data.napcat_login_info?.uin || '-'}</b></div>
        <div>昵称：<b>${data.napcat_login_info?.nick || '-'}</b></div>
        <div>当前全局卡片模式：<b>${data.card_mode?.label || '-'}</b></div>
        ${webuiUrl ? `<div>NapCat WebUI：<a style="color:#60a5fa" href="${webuiUrl}" target="_blank" rel="noopener">打开实时二维码</a></div>` : ''}
      `;
      document.getElementById('cardMode').innerText = `当前：${data.card_mode?.mode || '-'} / ${data.card_mode?.label || '-'}`;
      document.getElementById('cardModeSelect').value = data.card_mode?.mode || 'text';
      document.getElementById('raw').innerText = JSON.stringify(data, null, 2);
      document.getElementById('sideStatus').innerText = `OneBot: ${onebotOnline ? '在线' : '离线'} | NapCat: ${napcatOnline ? '在线' : '离线'}`;
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
    async function sendMsg() {
      const kind = document.getElementById('sendKind').value;
      const target = document.getElementById('sendTarget').value.trim();
      const text = document.getElementById('sendText').value;
      const image_url = document.getElementById('sendImageUrl').value.trim();
      if (!target) return;
      const data = await jpost('/panel/api/send', {kind, target_id: Number(target), text, image_url});
      document.getElementById('sendResult').innerText = JSON.stringify(data, null, 2);
    }
    function badge(label, ok) {
      return `<span class="badge ${ok ? 'ok' : 'bad'}">${ok ? '✅' : '❌'} ${label}</span>`;
    }
    function esc(s) {
      return (s || '').toString().replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[m] || m));
    }

    async function loadPlugins() {
      const data = await jget('/panel/api/plugins');
      const plugins = (data.plugins || {});
      const names = Object.keys(plugins).sort();

      // raw json for power users
      const simple = names.map(n => {
        const p = plugins[n] || {};
        const enabled = (p.enabled !== false);
        const version = p.version || '';
        const trigger = p.trigger || '';
        return {name: n, enabled, version, trigger};
      });
      document.getElementById('plugins').innerText = JSON.stringify(simple, null, 2);

      // human list
      const box = document.getElementById('pluginsList');
      box.innerHTML = '';
      for (const n of names) {
        const p = plugins[n] || {};
        const enabled = (p.enabled !== false);
        const version = p.version || '';
        const trigger = p.trigger || '';
        const desc = `v${version || '?'}${trigger ? ' · ' + trigger : ''}`;
        const el = document.createElement('div');
        el.className = 'item';
        el.innerHTML = `
          <div class="meta">
            <div class="name">${esc(n)}</div>
            <div class="desc">${esc(desc)}</div>
          </div>
          <div class="actions">
            <button class="${enabled ? 'secondary' : ''}" onclick="setPluginEnabled('${esc(n)}', ${enabled ? 'false' : 'true'})">${enabled ? '禁用' : '启用'}</button>
          </div>
        `;
        box.appendChild(el);
      }
    }

    async function setPluginEnabled(name, enabled) {
      const data = await jpost('/panel/api/plugins/toggle', {name, enabled});
      document.getElementById('pluginResult').innerText = `已保存：${name} -> ${enabled ? '启用' : '禁用'}（需要重启生效）`;
      await loadPlugins();
    }

    async function restartFromPlugins() {
      const data = await jpost('/panel/api/restart', {confirm: true});
      document.getElementById('pluginResult').innerText = '已请求重启，页面将刷新…';
      setTimeout(()=>location.reload(), 1200);
    }

    async function runSelfcheck() {
      const log_lines = Number(document.getElementById('selfcheckLines').value || '120');
      const data = await jpost('/panel/api/selfcheck', {log_lines});
      document.getElementById('selfcheck').innerText = JSON.stringify(data, null, 2);

      // human summary
      const onebotOnline = !!(data.onebot_get_status?.data?.online ?? data.onebot_get_status?.online);
      const napcatOnline = !!(data.napcat_login_info?.data?.online ?? data.napcat_login_info?.online);
      const portsOk = !!(data.ports && data.ports.includes(':9000'));
      const webuiUrl = data.napcat_webui_url || '';

      const badges = [
        badge('OneBot 在线', onebotOnline),
        badge('NapCat 在线', napcatOnline),
        badge('9000 端口监听', portsOk),
      ];
      document.getElementById('selfcheckBadges').innerHTML = badges.join(' ');

      let tips = [];
      if (!onebotOnline) tips.push('OneBot 可能离线：检查 NapCat/OneBot 配置与 3000 端口。');
      if (!napcatOnline) tips.push(`NapCat 可能离线：建议打开 WebUI 扫码/验证。${webuiUrl ? 'WebUI：' + webuiUrl : ''}`);
      const hits = data.napcat_log_hits || [];
      const lastHit = hits.length ? hits[hits.length-1] : '';
      if (lastHit) tips.push('最近日志线索：' + lastHit.slice(0, 180));
      if (!tips.length) tips.push('看起来一切正常。');
      document.getElementById('selfcheckSummary').innerText = tips.join('\n');
    }
    async function createBackup() {
      const include_sqlite = document.getElementById('backupIncludeSqlite').value === 'true';
      const data = await jpost('/panel/api/backup', {include_sqlite});
      document.getElementById('backup').innerText = JSON.stringify(data, null, 2);
      if (data.url) {
        // open download url in new tab
        window.open(data.url, '_blank');
      }
    }
    async function loadLogs() {
      const lines = Number(document.getElementById('logLines').value || '200');
      const data = await jget('/panel/api/logs?lines=' + encodeURIComponent(lines));
      document.getElementById('logs').innerText = data.content || '(空)';
    }
    function setActiveMenu(id) {
      for (const a of document.querySelectorAll('.menu a')) a.classList.remove('active');
      const el = document.getElementById(id);
      if (el) el.classList.add('active');
    }
    function showSection(name) {
      for (const s of document.querySelectorAll('.section')) s.classList.remove('active');
      const target = document.getElementById('sec-' + name);
      if (target) target.classList.add('active');
      setActiveMenu('m-' + name);
    }
    function route() {
      const h = (location.hash || '').replace('#','');
      const key = h || 'dashboard';
      const allowed = new Set(['dashboard','login','ops','plugins','market','backup','raw']);
      showSection(allowed.has(key) ? key : 'dashboard');
    }
    window.addEventListener('hashchange', route);

    route();
    async function loadMarket() {
      const data = await jget('/panel/api/market');
      document.getElementById('marketList').innerText = JSON.stringify(data, null, 2);
    }
    async function loadMarketInstalled() {
      const data = await jget('/panel/api/market/installed');
      document.getElementById('marketInstalled').innerText = JSON.stringify(data, null, 2);
    }
    async function marketInstall() {
      const name = document.getElementById('marketName').value.trim();
      if (!name) return;
      const data = await jpost('/panel/api/market/install', {name});
      document.getElementById('marketResult').innerText = JSON.stringify(data, null, 2);
      await loadMarketInstalled();
    }
    async function marketRemove() {
      const name = document.getElementById('marketName').value.trim();
      if (!name) return;
      const data = await jpost('/panel/api/market/remove', {name});
      document.getElementById('marketResult').innerText = JSON.stringify(data, null, 2);
      await loadMarketInstalled();
    }
    async function restartApp() {
      const data = await jpost('/panel/api/restart', {confirm: true});
      document.getElementById('marketResult').innerText = JSON.stringify(data, null, 2);
      setTimeout(()=>location.reload(), 1200);
    }

    loadStatus(); refreshQrcode(); loadLogs(); loadPlugins(); loadMarket(); loadMarketInstalled();
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
        "napcat_webui_url": _napcat_webui_url_for_request(request),
        "panel_login_state": _read_login_state(),
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
        _mark_login_action("export_qrcode")
        return _export_qrcode()
    except Exception as exc:
        _mark_login_action("export_qrcode_failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/send")
async def panel_send_message(request: Request, body: SendMessageRequest) -> dict[str, Any]:
    """Send a message via OneBot v11.

    This endpoint is intended for debugging / operations from the web panel.
    """
    _auth_guard(request)
    try:
        resp = await _send_via_onebot(
            kind=body.kind,
            target_id=int(body.target_id),
            text=body.text or "",
            image_url=body.image_url or "",
        )
        return {"ok": True, "response": resp}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/plugins")
async def panel_list_plugins(request: Request) -> dict[str, Any]:
    _auth_guard(request)
    return {
        "ok": True,
        "note": "This reflects registry metadata recorded at startup-time discovery; toggles affect next restart.",
        "plugins": list_plugin_registry(),
    }


@router.post("/api/plugins/toggle")
async def panel_toggle_plugin(request: Request, body: PanelPluginToggleRequest) -> dict[str, Any]:
    _auth_guard(request)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    set_plugin_enabled(name, bool(body.enabled))
    return {"ok": True, "name": name, "enabled": bool(body.enabled), "restart_required": True}


@router.post("/api/selfcheck")
async def panel_selfcheck(request: Request, body: SelfcheckRequest) -> dict[str, Any]:
    _auth_guard(request)

    # 1) basic HTTP probes
    onebot_probe: dict[str, Any]
    try:
        onebot_probe = await _onebot_post("get_status")
    except Exception as exc:
        onebot_probe = {"ok": False, "error": str(exc)}

    napcat_probe: dict[str, Any]
    try:
        napcat_probe = await _napcat_qqlogin_post("/api/QQLogin/GetQQLoginInfo")
    except Exception as exc:
        napcat_probe = {"ok": False, "error": str(exc)}

    # 2) ports
    ports_out = ""
    try:
        r = subprocess.run(["sh", "-lc", "ss -lntp | egrep ':(9000|3000|6099)\\b' || true"], capture_output=True, text=True, check=False)
        ports_out = (r.stdout or r.stderr or "").strip()
    except Exception as exc:
        ports_out = str(exc)

    # 3) napcat logs keyword scan
    logs = _tail_container_logs(NAPCAT_CONTAINER_NAME, lines=int(body.log_lines or 120))
    keywords = ["KickedOffLine", "登录已失效", "下线", "ErrCode", "二维码", "扫码", "验证", "online"]
    hits: list[str] = []
    for line in logs.splitlines()[-2000:]:
        if any(k in line for k in keywords):
            hits.append(line)
    hits = hits[-80:]

    return {
        "ok": True,
        "now": int(time.time()),
        "onebot_get_status": onebot_probe,
        "napcat_login_info": napcat_probe,
        "ports": ports_out,
        "napcat_log_hits": hits,
        "napcat_webui_url": _napcat_webui_url_for_request(request),
    }


@router.post("/api/backup")
async def panel_create_backup(request: Request, body: BackupRequest) -> dict[str, Any]:
    _auth_guard(request)
    return _backup_runtime(include_sqlite=bool(body.include_sqlite))


@router.get("/api/backup/download")
async def panel_download_backup(request: Request, file: str = Query(...)) -> FileResponse:
    _auth_guard(request)
    name = Path(file).name
    p = PANEL_BACKUP_DIR / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(p, filename=name)


@router.get("/api/market")
async def panel_market_list(request: Request) -> dict[str, Any]:
    _auth_guard(request)
    items = list_market_plugins()
    return {
        "ok": True,
        "count": len(items),
        "plugins": [
            {
                "name": p.name,
                "version": p.version,
                "author": p.author,
                "description": p.description,
                "url": p.url,
                "sha256": bool((p.sha256 or "").strip()),
            }
            for p in items
        ],
    }


@router.get("/api/market/installed")
async def panel_market_installed(request: Request) -> dict[str, Any]:
    _auth_guard(request)
    data = _load_market_installed().get("installed", {})
    return {"ok": True, "installed": data}


@router.post("/api/market/install")
async def panel_market_install(request: Request, body: MarketInstallRequest) -> dict[str, Any]:
    _auth_guard(request)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    item = get_market_plugin(name)
    if not item:
        raise HTTPException(status_code=404, detail="plugin not found in market")
    if not (item.url or "").strip():
        raise HTTPException(status_code=400, detail="market item url missing")

    # download
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(item.url)
        resp.raise_for_status()
        content = resp.content

    got = hashlib.sha256(content).hexdigest()
    expected = (item.sha256 or "").strip()
    if expected and expected != got:
        raise HTTPException(status_code=400, detail="sha256 mismatch")

    filename = _safe_market_filename(item.name)
    target = (BASE_DIR / "user_plugins") / filename
    target.write_bytes(content)

    installed = _load_market_installed()
    installed.setdefault("installed", {})[item.name] = {
        "name": item.name,
        "file": filename,
        "url": item.url,
        "version": item.version,
        "author": item.author,
        "sha256": got,
    }
    _save_market_installed(installed)

    return {"ok": True, "name": item.name, "file": filename, "version": item.version, "restart_required": True}


@router.post("/api/market/remove")
async def panel_market_remove(request: Request, body: MarketRemoveRequest) -> dict[str, Any]:
    _auth_guard(request)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    installed = _load_market_installed()
    info = (installed.get("installed", {}) or {}).get(name)
    if not info:
        raise HTTPException(status_code=404, detail="not installed")

    file = str(info.get("file") or "")
    if file:
        p = (BASE_DIR / "user_plugins") / file
        if p.exists():
            try:
                p.rename(p.with_suffix(p.suffix + ".disabled"))
            except Exception:
                pass

    (installed.get("installed", {}) or {}).pop(name, None)
    _save_market_installed(installed)

    return {"ok": True, "name": name, "restart_required": True}


@router.post("/api/restart")
async def panel_restart(request: Request, body: RestartRequest) -> dict[str, Any]:
    _auth_guard(request)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm required")

    # We run under uvicorn; easiest is to kill the current process.
    # Supervisor/nohup will be restarted by ops script; in our setup we relaunch from shell.
    # Here we just exit the process.
    _mark_login_action("restart_requested")
    import os

    os._exit(0)


@router.get("/qrcode.png")
async def panel_qrcode_image(request: Request) -> FileResponse:
    _auth_guard(request)
    # Always export the latest qrcode before serving.
    # QR code validity is short; serving a cached file causes "arrive expired".
    _export_qrcode()
    return FileResponse(PANEL_QRCODE_PATH)
