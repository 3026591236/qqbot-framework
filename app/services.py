from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.db import get_conn


BASE_REWARD = 1
MAX_STREAK_BONUS = 4
MAKEUP_COST = 2
APP_TZ = ZoneInfo("Asia/Shanghai")


def _scope_group_id(group_id: int | None) -> int:
    return group_id or 0


def _now() -> datetime:
    return datetime.now(APP_TZ)


def _today() -> datetime.date:
    return _now().date()


def _parse_date(raw: str | None):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        return None


def _bonus_for_streak(streak: int) -> int:
    if streak <= 1:
        return 0
    return min(MAX_STREAK_BONUS, streak // 3)


def _scope_name(group_id: int | None) -> str:
    return "本群" if group_id else "私聊"


def _get_user_row(conn, user_id: int, gid: int):
    return conn.execute(
        "SELECT * FROM user_points WHERE user_id=? AND group_id=?",
        (user_id, gid),
    ).fetchone()


def get_points(user_id: int, group_id: int | None) -> int:
    gid = _scope_group_id(group_id)
    with get_conn() as conn:
        row = _get_user_row(conn, user_id, gid)
        return int(row["points"]) if row else 0


def get_checkin_status(user_id: int, group_id: int | None) -> dict:
    gid = _scope_group_id(group_id)
    with get_conn() as conn:
        row = _get_user_row(conn, user_id, gid)
        if row is None:
            return {
                "scope": _scope_name(group_id),
                "points": 0,
                "streak": 0,
                "total_checkins": 0,
                "last_checkin_at": None,
                "signed_today": False,
                "can_makeup": False,
            }

        last_date = _parse_date(row["last_checkin_at"])
        today = _today()
        yesterday = today - timedelta(days=1)
        return {
            "scope": _scope_name(group_id),
            "points": int(row["points"]),
            "streak": int(row["checkin_streak"] or 0),
            "total_checkins": int(row["total_checkins"] or 0),
            "last_checkin_at": row["last_checkin_at"],
            "signed_today": last_date == today,
            "can_makeup": last_date == yesterday - timedelta(days=1),
        }


def daily_checkin(user_id: int, group_id: int | None, reward: int = BASE_REWARD) -> dict:
    gid = _scope_group_id(group_id)
    today = _today()
    yesterday = today - timedelta(days=1)
    now = _now().isoformat(timespec="seconds")

    with get_conn() as conn:
        row = _get_user_row(conn, user_id, gid)

        if row is None:
            streak = 1
            bonus = _bonus_for_streak(streak)
            gained = reward + bonus
            conn.execute(
                "INSERT INTO user_points (user_id, group_id, points, last_checkin_at, checkin_streak, total_checkins, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, gid, gained, today.isoformat(), streak, 1, now),
            )
            return {
                "ok": True,
                "already": False,
                "scope": _scope_name(group_id),
                "points": gained,
                "gained": gained,
                "base_reward": reward,
                "bonus": bonus,
                "streak": streak,
                "total_checkins": 1,
            }

        points = int(row["points"])
        last_date = _parse_date(row["last_checkin_at"])
        streak = int(row["checkin_streak"] or 0)
        total = int(row["total_checkins"] or 0)

        if last_date == today:
            return {
                "ok": False,
                "already": True,
                "scope": _scope_name(group_id),
                "points": points,
                "gained": 0,
                "base_reward": reward,
                "bonus": 0,
                "streak": streak,
                "total_checkins": total,
            }

        if last_date == yesterday:
            streak += 1
        else:
            streak = 1

        bonus = _bonus_for_streak(streak)
        gained = reward + bonus
        points += gained
        total += 1
        conn.execute(
            "UPDATE user_points SET points=?, last_checkin_at=?, checkin_streak=?, total_checkins=?, updated_at=? WHERE user_id=? AND group_id=?",
            (points, today.isoformat(), streak, total, now, user_id, gid),
        )
        return {
            "ok": True,
            "already": False,
            "scope": _scope_name(group_id),
            "points": points,
            "gained": gained,
            "base_reward": reward,
            "bonus": bonus,
            "streak": streak,
            "total_checkins": total,
        }


def makeup_checkin(user_id: int, group_id: int | None, cost: int = MAKEUP_COST, reward: int = BASE_REWARD) -> dict:
    gid = _scope_group_id(group_id)
    today = _today()
    yesterday = today - timedelta(days=1)
    before_yesterday = today - timedelta(days=2)
    now = _now().isoformat(timespec="seconds")

    with get_conn() as conn:
        row = _get_user_row(conn, user_id, gid)
        if row is None:
            return {"ok": False, "reason": "no_record", "message": "你还没有签到记录，不能补签"}

        points = int(row["points"])
        last_date = _parse_date(row["last_checkin_at"])
        streak = int(row["checkin_streak"] or 0)
        total = int(row["total_checkins"] or 0)

        if last_date == today:
            return {"ok": False, "reason": "already_today", "message": "今天已经签到了，不需要补签"}
        if last_date != before_yesterday:
            return {"ok": False, "reason": "not_eligible", "message": "当前只支持补昨天的断签"}
        if points < cost:
            return {"ok": False, "reason": "not_enough_points", "message": f"补签需要 {cost} 积分，你当前积分不足"}

        streak += 2
        bonus = _bonus_for_streak(streak)
        gained = reward + bonus
        points = points - cost + gained
        total += 1
        conn.execute(
            "UPDATE user_points SET points=?, last_checkin_at=?, checkin_streak=?, total_checkins=?, updated_at=? WHERE user_id=? AND group_id=?",
            (points, yesterday.isoformat(), streak, total, now, user_id, gid),
        )
        return {
            "ok": True,
            "scope": _scope_name(group_id),
            "points": points,
            "cost": cost,
            "gained": gained,
            "bonus": bonus,
            "streak": streak,
            "total_checkins": total,
        }


def get_points_ranking(group_id: int | None, limit: int = 10) -> list[dict]:
    gid = _scope_group_id(group_id)
    limit = max(1, min(50, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, points, checkin_streak, total_checkins, last_checkin_at FROM user_points WHERE group_id=? ORDER BY points DESC, checkin_streak DESC, user_id ASC LIMIT ?",
            (gid, limit),
        ).fetchall()
        return [dict(row) for row in rows]
