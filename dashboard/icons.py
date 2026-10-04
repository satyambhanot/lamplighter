"""A small, consistent icon set for the dashboard — hand-drawn minimal
line icons (not a third-party library), so there's no licensing
question and no extra dependency. All 24x24 viewBox, 1.8px stroke,
round joins, inherit color via currentColor.
"""

from __future__ import annotations

_PATHS: dict[str, str] = {
    "map-pin": '<path d="M12 21s7-6.4 7-12a7 7 0 1 0-14 0c0 5.6 7 12 7 12Z"/><circle cx="12" cy="9" r="2.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "route": '<circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="5.5" r="2.5"/><path d="M8 18.5h5a4 4 0 0 0 4-4v-1a4 4 0 0 0-4-4H9a4 4 0 0 1-4-4v-.5"/>',
    "alert-triangle": '<path d="M12 4 2.5 20.5h19Z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.6 2.6L16.5 9"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.4-4.4"/>',
    "sliders": '<path d="M5 7h7M16 7h3M5 17h3M12 17h7"/><circle cx="14" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    "download": '<path d="M12 4v11M8 11l4 4 4-4"/><path d="M5 19h14"/>',
    "graduation-cap": '<path d="M2 9.5 12 5l10 4.5L12 14 2 9.5Z"/><path d="M6.5 11.8v4.3c0 1.3 2.5 2.4 5.5 2.4s5.5-1.1 5.5-2.4v-4.3"/>',
    "bus": '<rect x="4" y="5" width="16" height="12" rx="2.5"/><path d="M4 12h16M7 17v2M17 17v2"/><circle cx="8" cy="9" r=".6" fill="currentColor" stroke="none"/><circle cx="16" cy="9" r=".6" fill="currentColor" stroke="none"/>',
    "zap": '<path d="M12 2 4 14h6l-1 8 9-13h-6z"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
    "activity": '<path d="M3 12h4l2.5-7L13 19l2.5-7H21"/>',
    "map": '<path d="M9 4 4 6v14l5-2 6 2 5-2V4l-5 2-6-2Z"/><path d="M9 4v14M15 6v14"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17.5" cy="9" r="2.5"/><path d="M15 20c.1-2.4 1.5-4.4 3.5-5.3"/>',
    "shield": '<path d="M12 3 5 6v6c0 4.5 3 7.7 7 9 4-1.3 7-4.5 7-9V6Z"/>',
    "calendar": '<rect x="4" y="5.5" width="16" height="15" rx="2.5"/><path d="M4 10h16M8 3.5v4M16 3.5v4"/>',
    "lamp": '<circle cx="12" cy="8.5" r="5.5"/><path d="M12 14v4.5M9 21.5h6M9.8 8.5h4.4"/>',
}


def icon(name: str, size: int = 16, color: str = "currentColor", stroke: float = 1.8) -> str:
    """Return an inline <span class="icon">...SVG...</span> for ``name``.

    Returns an empty string for an unknown icon name rather than raising
    — a missing icon shouldn't break a page render.
    """
    body = _PATHS.get(name)
    if body is None:
        return ""
    return (
        f'<span class="icon" style="width:{size}px;height:{size}px">'
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg></span>"
    )
