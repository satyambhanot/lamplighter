"""Dispatcher note: a short paragraph summarizing the current week's plan.

Uses the Anthropic API if ANTHROPIC_API_KEY is set, otherwise falls back
to a plain template so the demo never depends on the key or a network
call. Implemented in Phase 5.
"""

from __future__ import annotations

import pandas as pd


def dispatcher_note(plan: pd.DataFrame, skipped: pd.DataFrame, crew_cut_pct: float | None = None) -> str:
    """Write a short paragraph: which lights were picked and the top
    reasons, what was skipped, and the crew-cut impact if any.

    Only computed facts from ``plan``/``skipped`` are passed to the LLM;
    the prompt instructs it not to add anything else.

    Args:
        plan: This week's selected lights (with ``reasons``).
        skipped: Lights that didn't fit the budget this week.
        crew_cut_pct: If set, the reduced budget fraction to mention.

    Returns:
        A short plain-text paragraph.
    """
    raise NotImplementedError("Phase 5")


def _template_note(plan: pd.DataFrame, skipped: pd.DataFrame, crew_cut_pct: float | None) -> str:
    """Fallback used when no ANTHROPIC_API_KEY is configured."""
    raise NotImplementedError("Phase 5")
