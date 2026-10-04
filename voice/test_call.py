"""Run a text-only test call against the real ElevenLabs agent.

ElevenLabs plays a simulated caller against the real agent and prompt.
The simulate endpoint never calls webhooks, so each scenario returns a
mocked tool result copied from a real API response. This tests how the
agent talks and reads results; only a browser call exercises the tunnel.

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

from api.service import check_hazard
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
    "other_city": (
        "You are calling about a street light that is out on Jasper Avenue in downtown Edmonton, near 104 "
        "Street. Insist it is in Edmonton if asked. Follow whatever the agent suggests and end the call."
    ),
    "emergency": (
        "You are panicking. A car just crashed into a street light pole on 17 Avenue SW in Calgary and the "
        "driver is bleeding and not moving. Tell the agent this in your first answer and ask what to do. "
        "Follow the agent's instructions and end the call."
    ),
    "conrich": (
        "You are calling about a street light that is out near Khalsa School on Conrich Road, at Township Road "
        "250. If asked, say it is in Conrich. Follow whatever the agent suggests and end the call."
    ),
    "no_hazard": (
        "You are calling to report a street light that is out near King George School. Confirm the location "
        "when it is read back. When asked about hazards, say clearly: the pole is standing, there are no "
        "exposed wires and no sparking. Listen to the answer, thank the agent, and end the call."
    ),
    "not_found": (
        "You are calling about a street light that is out near the Glenbrook corner store. Confirm it when "
        "read back and say there are no hazards. If the agent cannot find it, say the street address is "
        "3401 37 Street SW. Listen to the answer and end the call."
    ),
}

# The agent must not call any tool in these scenarios.
NO_TOOL_SCENARIOS = {"other_city", "emergency", "conrich"}
# The API's hazard check must not flag the description sent to report_light.
NO_HAZARD_WORDS_SCENARIOS = {"no_hazard", "not_found"}
# After a not-found result the agent must not ask for an intersection.
NO_INTERSECTION_SCENARIOS = {"not_found"}

# The API's answer when a location cannot be geocoded.
NOT_FOUND = {
    "ticket_id": None,
    "merged": False,
    "hazard": False,
    "needs_clarification": True,
    "rank": None,
    "old_rank": None,
    "expected_fix_date": None,
    "message": "Please provide a street address or a well-known place nearby.",
}

# Real responses recorded from this API on Oct 3 (demo clock Aug 24, 2026).
MOCK_RESULTS = {
    "report": {
        "report_light": {
            "ticket_id": "L-5b790e96b0b3",
            "merged": False,
            "hazard": False,
            "needs_clarification": False,
            "rank": 10,
            "old_rank": None,
            "expected_fix_date": "2026-08-31",
            "message": "New report entered at priority #10.",
        }
    },
    "status": {
        "check_status": {
            "ticket_id": "L-5b790e96b0b3",
            "rank": 5,
            "expected_fix_date": "2026-08-31",
            "status": "open",
        }
    },
    "hazard": {
        "report_light": {
            "ticket_id": "L-de630528e6b0",
            "merged": False,
            "hazard": True,
            "needs_clarification": False,
            "rank": None,
            "old_rank": None,
            "expected_fix_date": None,
            "message": "Report flagged for urgent dispatcher review.",
        }
    },
    # Returned only if the agent wrongly files these calls anyway.
    "other_city": {
        "report_light": {
            "ticket_id": None,
            "merged": False,
            "hazard": False,
            "needs_clarification": True,
            "rank": None,
            "old_rank": None,
            "expected_fix_date": None,
            "message": "Please provide a street address or a well-known place nearby.",
        }
    },
    "conrich": {"report_light": NOT_FOUND},
    "no_hazard": {
        "report_light": {
            "ticket_id": "L-015a9ab2270c",
            "merged": False,
            "hazard": False,
            "needs_clarification": False,
            "rank": 10,
            "old_rank": None,
            "expected_fix_date": "2026-09-01",
            "message": "New report entered at priority #10.",
        }
    },
    "not_found": {"report_light": NOT_FOUND},
    "emergency": {
        "report_light": {
            "ticket_id": "L-de630528e6b0",
            "merged": False,
            "hazard": True,
            "needs_clarification": False,
            "rank": None,
            "old_rank": None,
            "expected_fix_date": None,
            "message": "Report flagged for urgent dispatcher review.",
        }
    },
}


def simulate(api_key: str, agent_id: str, scenario: str) -> dict:
    mocks = {
        tool: {"default_return_value": json.dumps(result), "default_is_error": False}
        for tool, result in MOCK_RESULTS[scenario].items()
    }
    body = {
        "simulation_specification": {
            "simulated_user_config": {"prompt": {"prompt": SCENARIOS[scenario]}},
            "tool_mock_config": mocks,
        },
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
    result = simulate(api_key, agent_id, args.scenario)
    if args.save:
        with open(args.save, "w") as handle:
            json.dump(result, handle, indent=2)
    print("\n".join(transcript_lines(result)))
    if args.scenario in NO_TOOL_SCENARIOS:
        called = [
            call.get("tool_name")
            for turn in result.get("simulated_conversation", [])
            for call in turn.get("tool_calls") or []
        ]
        verdict = "PASS: no tool called" if not called else f"FAIL: agent called {called}"
        print(verdict)
    turns = result.get("simulated_conversation", [])
    if args.scenario in NO_HAZARD_WORDS_SCENARIOS:
        descriptions = [
            json.loads(call.get("params_as_json") or "{}").get("description", "")
            for turn in turns
            for call in turn.get("tool_calls") or []
            if call.get("tool_name") == "report_light"
        ]
        flagged = [d for d in descriptions if check_hazard(d)]
        if not descriptions:
            print("FAIL: report_light was never called")
        else:
            print("PASS: the API would not flag it as a hazard" if not flagged else f"FAIL: {flagged}")
    if args.scenario in NO_INTERSECTION_SCENARIOS:
        seen_result, asked = False, []
        for turn in turns:
            if turn.get("tool_results"):
                seen_result = True
            message = (turn.get("message") or "").lower()
            if seen_result and turn.get("role") == "agent" and "intersection" in message:
                asked.append(turn["message"])
        print("PASS: never asked for an intersection" if not asked else f"FAIL: {asked}")


if __name__ == "__main__":
    main()
