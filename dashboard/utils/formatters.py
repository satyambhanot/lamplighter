"""Consistent formatting for timestamps and untrusted API text."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape


def safe_text(value: object, fallback: str = "—") -> str:
    text = str(value).strip() if value is not None else ""
    return escape(text) if text else fallback


def relative_time(value: str) -> tuple[str, str]:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        seconds = max(0, int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()))
    except (ValueError, TypeError):
        return "Unknown time", str(value)
    if seconds < 60:
        label = "Just now"
    elif seconds < 3600:
        label = f"{seconds // 60} min ago"
    elif seconds < 86400:
        label = f"{seconds // 3600} hr ago"
    else:
        label = dt.strftime("%b %d, %Y")
    return label, dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
