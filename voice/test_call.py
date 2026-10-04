"""Run a text-only test call against the real ElevenLabs agent.

ElevenLabs plays a simulated caller; the agent's tools call our API through
the tunnel for real, so the light shows up on the dashboard.

Run with: python -m voice.test_call --scenario report   (or status, hazard)
Needs make api, make tunnel and make voice first. Each run uses credits.
"""

from __future__ import annotations

import argparse
import json
import logging
import os

import requests
from dotenv import load_dotenv

from voice.setup_agent import AGENT_ID_KEY, API_BASE_URL, ENV_PATH

logger = logging.getLogger(__name__)

SIMULATION_TIMEOUT_SECONDS = 180
MAX_TURNS = 12

SCENARIOS = {
    "report": (
        "You are a Calgary resident calling to report a street light that is out near King George School. "
        "When the agent reads the location back, confirm it. The pole is standing and you see no wires or "
        "sparks. Listen to the queue position and repair week, thank the agent, and end the call."
    ),
    "status": (
        "You are a Calgary resident who reported a broken street light earlier today. "
        "Ask the agent for the status of your report. Listen to the answer, thank the agent, and end the call."
    ),
    "hazard": (
        "You are a Calgary resident calling about a street light outside City Hall. "
        "When the agent reads the location back, confirm it. When asked, say the pole has been knocked down "
        "and there are exposed wires on the sidewalk. Follow the agent's safety advice and end the call."
    ),
}


def simulate(api_key: str, agent_id: str, caller_prompt: str) -> dict:
    body = {
        "simulation_specification": {"simulated_user_config": {"prompt": {"prompt": caller_prompt}}},
        "new_turns_limit": MAX_TURNS,
    }
    response = requests.post(
        f"{API_BASE_URL}/v1/convai/agents/{agent_id}/simulate-conversation",
        headers={"xi-api-key": api_key},
        json=body,
        timeout=SIMULATION_TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        raise SystemExit(f"Simulation failed with {response.status_code}: {response.text[:500]}")
    return response.json()


def transcript_lines(result: dict) -> list[str]:
    """Readable transcript: spoken turns plus each tool call and result."""
    lines = []
    for turn in result.get("simulated_conversation", []):
        for call in turn.get("tool_calls") or []:
            lines.append(f"  [tool call] {call.get('tool_name')} {call.get('params_as_json')}")
        for tool_result in turn.get("tool_results") or []:
            flag = " ERROR" if tool_result.get("is_error") else ""
            lines.append(
                f"  [tool result{flag}] {tool_result.get('tool_name')} {tool_result.get('result_value')}"
            )
        if turn.get("message"):
            lines.append(f"{turn['role'].upper()}: {turn['message']}")
    return lines


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="report")
    parser.add_argument("--save", help="also write the raw response JSON to this path")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    api_key, agent_id = os.environ.get("ELEVENLABS_API_KEY"), os.environ.get(AGENT_ID_KEY)
    if not api_key or not agent_id:
        raise SystemExit("Missing ELEVENLABS_API_KEY or ELEVENLABS_AGENT_ID in .env. Run make voice first.")

    logger.info("Simulating a '%s' call; this takes up to a minute", args.scenario)
    result = simulate(api_key, agent_id, SCENARIOS[args.scenario])
    if args.save:
        with open(args.save, "w") as handle:
            json.dump(result, handle, indent=2)
    print("\n".join(transcript_lines(result)))


if __name__ == "__main__":
    main()
