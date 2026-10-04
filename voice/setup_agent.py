"""Create or update the Lamplighter ElevenLabs agent and its two webhook tools.

Run with: make voice  (after make configure, with ELEVENLABS_API_KEY and
NGROK_DOMAIN in .env, and make api + make tunnel running).

Safe to re-run: IDs are saved in .env after the first run, and later runs
update the same secret, tools and agent instead of creating new ones.
Keys are never logged.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

from config import ROOT_DIR

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.elevenlabs.io"
REQUEST_TIMEOUT_SECONDS = 30
ENV_PATH = ROOT_DIR / ".env"
TOOLS_JSON = ROOT_DIR / "voice" / "tools.json"
PROMPT_MD = ROOT_DIR / "voice" / "system_prompt.md"

AGENT_NAME = "Lamplighter street light line"
AGENT_TAG = "lamplighter"
SECRET_NAME = "lamplighter_voice_secret"
FIRST_MESSAGE = (
    "Hi, this is Lamplighter, Calgary's street light line. "
    "Are you reporting a light that's out, or checking on one you already reported?"
)

REQUIRED_ENV = ("ELEVENLABS_API_KEY", "VOICE_SHARED_SECRET", "NGROK_DOMAIN")
SECRET_ID_KEY = "ELEVENLABS_VOICE_SECRET_ID"
AGENT_ID_KEY = "ELEVENLABS_AGENT_ID"
TOOL_ID_KEYS = {"report_light": "ELEVENLABS_REPORT_TOOL_ID", "check_status": "ELEVENLABS_STATUS_TOOL_ID"}


class SetupError(Exception):
    """A setup step failed; the message says what to fix."""


class NotFound(SetupError):
    """The ElevenLabs object behind a saved ID no longer exists."""


def public_url(domain: str) -> str:
    """Turn NGROK_DOMAIN (with or without a scheme) into https://host."""
    host = domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not host:
        raise SetupError("NGROK_DOMAIN is empty")
    return f"https://{host}"


def load_prompt(path: Path = PROMPT_MD) -> str:
    return path.read_text()


def load_tool_configs(base_url: str, secret_id: str, path: Path = TOOLS_JSON) -> list[dict]:
    """Read voice/tools.json and fill in the tunnel URL and secret ID."""
    raw = path.read_text().replace("{PUBLIC_URL}", base_url).replace("{VOICE_SECRET_ID}", secret_id)
    return json.loads(raw)["tools"]


def agent_payload(prompt: str, tool_ids: list[str]) -> dict:
    return {
        "name": AGENT_NAME,
        "tags": [AGENT_TAG],
        "conversation_config": {
            "agent": {
                "first_message": FIRST_MESSAGE,
                "language": "en",
                "prompt": {"prompt": prompt, "tool_ids": tool_ids},
            }
        },
    }


class ElevenLabsClient:
    """Minimal JSON client for the ElevenLabs Agents API."""

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self._api_key = api_key
        self._session = session or requests.Session()

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        response = self._session.request(
            method,
            API_BASE_URL + path,
            headers={"xi-api-key": self._api_key},
            json=body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            raise NotFound(f"{method} {path} returned 404")
        if response.status_code >= 400:
            raise SetupError(f"{method} {path} failed with {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else {}


def upsert_secret(client: ElevenLabsClient, secret_id: str | None, value: str) -> str:
    """Store VOICE_SHARED_SECRET as an ElevenLabs workspace secret."""
    if secret_id:
        try:
            client.request(
                "PATCH",
                f"/v1/convai/secrets/{secret_id}",
                {"type": "update", "name": SECRET_NAME, "value": value},
            )
            return secret_id
        except NotFound:
            logger.warning("Saved secret %s no longer exists; creating a new one", secret_id)
    created = client.request(
        "POST", "/v1/convai/secrets", {"type": "new", "name": SECRET_NAME, "value": value}
    )
    return created["secret_id"]


def upsert_tool(client: ElevenLabsClient, tool_id: str | None, tool_config: dict) -> str:
    if tool_id:
        try:
            client.request("PATCH", f"/v1/convai/tools/{tool_id}", {"tool_config": tool_config})
            return tool_id
        except NotFound:
            logger.warning("Saved tool %s no longer exists; creating a new one", tool_id)
    return client.request("POST", "/v1/convai/tools", {"tool_config": tool_config})["id"]


def upsert_agent(client: ElevenLabsClient, agent_id: str | None, payload: dict) -> str:
    if agent_id:
        try:
            client.request("PATCH", f"/v1/convai/agents/{agent_id}", payload)
            return agent_id
        except NotFound:
            logger.warning("Saved agent %s no longer exists; creating a new one", agent_id)
    return client.request("POST", "/v1/convai/agents/create", payload)["agent_id"]


def check_tunnel(base_url: str) -> None:
    """Fail early if the public URL does not reach a running API."""
    try:
        response = requests.get(
            base_url + "/health", headers={"ngrok-skip-browser-warning": "true"}, timeout=10
        )
    except requests.RequestException as exc:
        raise SetupError(f"Cannot reach {base_url}/health ({exc}). Start make api and make tunnel.") from exc
    if response.status_code != 200:
        raise SetupError(
            f"{base_url}/health returned {response.status_code}. Start make api and make tunnel."
        )


def configure(client: ElevenLabsClient, env: dict[str, str | None]) -> dict[str, str]:
    """Create or update the secret, both tools and the agent.

    Returns the IDs to save, keyed by their .env names.
    """
    base_url = public_url(env["NGROK_DOMAIN"] or "")
    ids: dict[str, str] = {}
    ids[SECRET_ID_KEY] = upsert_secret(client, env.get(SECRET_ID_KEY), env["VOICE_SHARED_SECRET"] or "")
    logger.info("Voice secret ready")

    tool_ids = []
    for tool_config in load_tool_configs(base_url, ids[SECRET_ID_KEY]):
        key = TOOL_ID_KEYS[tool_config["name"]]
        ids[key] = upsert_tool(client, env.get(key), tool_config)
        tool_ids.append(ids[key])
        logger.info("Tool %s points at %s", tool_config["name"], tool_config["api_schema"]["url"])

    ids[AGENT_ID_KEY] = upsert_agent(client, env.get(AGENT_ID_KEY), agent_payload(load_prompt(), tool_ids))
    logger.info("Agent ready: %s", ids[AGENT_ID_KEY])
    return ids


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--skip-tunnel-check", action="store_true", help="configure even if the tunnel is down"
    )
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    env = {
        key: os.environ.get(key)
        for key in (*REQUIRED_ENV, SECRET_ID_KEY, AGENT_ID_KEY, *TOOL_ID_KEYS.values())
    }
    missing = [key for key in REQUIRED_ENV if not env[key]]
    if missing:
        raise SystemExit(f"Missing in .env: {', '.join(missing)}. See voice/SETUP.md.")

    try:
        if not args.skip_tunnel_check:
            check_tunnel(public_url(env["NGROK_DOMAIN"] or ""))
        ids = configure(ElevenLabsClient(env["ELEVENLABS_API_KEY"] or ""), env)
    except SetupError as exc:
        raise SystemExit(f"Voice setup failed: {exc}") from exc

    for key, value in ids.items():
        set_key(ENV_PATH, key, value)
    ENV_PATH.chmod(0o600)
    logger.info(
        "Saved agent, tool and secret IDs to .env. Open ElevenLabs > Agents > %s to test a call.", AGENT_NAME
    )


if __name__ == "__main__":
    main()
