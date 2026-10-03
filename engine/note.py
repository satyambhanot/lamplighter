"""Dispatcher note: a short paragraph summarizing the current week's plan.

Uses the Anthropic API if ANTHROPIC_API_KEY is set, otherwise falls back
to a plain template so the demo never depends on the key or a network
call.
"""

from __future__ import annotations

import json
import logging
import os

import pandas as pd

from config import ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

NOTE_SYSTEM_PROMPT = (
    "You write short dispatcher notes for a city street-light repair crew's "
    "weekly plan. Use ONLY the facts given to you as JSON — never add a "
    "number, location, or claim that isn't in them. Two to four plain-text "
    "sentences, no markdown, no greeting, no sign-off."
)


def _facts(plan: pd.DataFrame, skipped: pd.DataFrame, crew_cut_pct: float | None) -> dict:
    """Computed facts for the note — the only things the LLM may draw on."""
    facts: dict = {
        "n_planned": len(plan),
        "n_skipped": len(skipped),
        "damage_count": int(plan["is_damage"].sum()) if "is_damage" in plan and not plan.empty else 0,
        "school_count": int(plan["near_school"].sum()) if "near_school" in plan and not plan.empty else 0,
        "transit_count": int(plan["near_transit"].sum()) if "near_transit" in plan and not plan.empty else 0,
        "top_communities": (
            plan["comm_name"].value_counts().head(3).to_dict() if "comm_name" in plan and not plan.empty else {}
        ),
        "crew_cut_pct": crew_cut_pct,
        "closest_miss_reason": None,
    }
    if not skipped.empty and "reasons" in skipped:
        facts["closest_miss_reason"] = skipped["reasons"].iloc[0]
    return facts


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
    facts = _facts(plan, skipped, crew_cut_pct)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return _llm_note(facts, api_key)
        except Exception:
            logger.exception("Anthropic API call failed; falling back to template")

    return _template_note(facts)


def _llm_note(facts: dict, api_key: str) -> str:
    """Real Anthropic call. Any failure (no network, bad key, rate
    limit, ...) is caught by the caller, which falls back to the
    template — the demo must never depend on this succeeding.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=200,
        system=NOTE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Facts (JSON): {json.dumps(facts)}"}],
    )
    return response.content[0].text.strip()


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _template_note(facts: dict) -> str:
    """Fallback used when no ANTHROPIC_API_KEY is configured, or the
    API call failed.
    """
    if facts["n_planned"] == 0:
        return "No lights are scheduled to be fixed this week."

    parts = [f"This week the crew is fixing {_plural(facts['n_planned'], 'light')}."]

    highlights = []
    if facts["damage_count"]:
        highlights.append(_plural(facts["damage_count"], "damage report"))
    if facts["school_count"]:
        highlights.append(f"{_plural(facts['school_count'], 'light')} near schools")
    if facts["transit_count"]:
        highlights.append(f"{_plural(facts['transit_count'], 'light')} near transit stops")
    if highlights:
        parts.append("Priorities include " + ", ".join(highlights) + ".")

    if facts["top_communities"]:
        communities = ", ".join(facts["top_communities"].keys())
        parts.append(f"Most visits are in {communities}.")

    if facts["n_skipped"]:
        parts.append(f"{_plural(facts['n_skipped'], 'light')} didn't fit this week's route and roll over to next week.")

    if facts["crew_cut_pct"] is not None:
        parts.append(
            f"Crew capacity is reduced to {facts['crew_cut_pct']:.0%} this week, so fewer lights than usual are being fixed."
        )

    return " ".join(parts)
