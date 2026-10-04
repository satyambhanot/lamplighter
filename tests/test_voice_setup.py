"""Voice agent setup builds the right ElevenLabs payloads and never leaks keys."""

import json

import pytest

from voice import setup_agent
from voice.setup_agent import ElevenLabsClient, configure, load_tool_configs, public_url

ENV = {
    "ELEVENLABS_API_KEY": "el-key-test",
    "VOICE_SHARED_SECRET": "voice-secret-value",
    "NGROK_DOMAIN": "demo.ngrok-free.app",
}


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Records requests and answers like the ElevenLabs API."""

    def __init__(self, missing: set[str] = frozenset()) -> None:
        self.calls: list[tuple[str, str, dict | None, dict]] = []
        self.missing = missing

    def request(self, method, url, headers, json, timeout):
        path = url.removeprefix(setup_agent.API_BASE_URL)
        self.calls.append((method, path, json, headers))
        if any(path.endswith(item) for item in self.missing):
            return FakeResponse(404, {"detail": "not found"})
        if (method, path) == ("POST", "/v1/convai/secrets"):
            return FakeResponse(200, {"secret_id": "sec-1", "name": json["name"], "type": "stored"})
        if (method, path) == ("POST", "/v1/convai/tools"):
            return FakeResponse(200, {"id": f"tool-{json['tool_config']['name']}"})
        if (method, path) == ("POST", "/v1/convai/agents/create"):
            return FakeResponse(200, {"agent_id": "agent-1"})
        return FakeResponse(200, {})


def test_public_url_accepts_bare_or_scheme_domain():
    assert public_url("demo.ngrok-free.app") == "https://demo.ngrok-free.app"
    assert public_url("https://demo.ngrok-free.app/") == "https://demo.ngrok-free.app"


def test_tool_configs_use_tunnel_secret_and_fixed_phone():
    tools = {tool["name"]: tool for tool in load_tool_configs("https://demo.ngrok-free.app", "sec-1")}
    report, status = tools["report_light"], tools["check_status"]
    assert report["api_schema"]["url"] == "https://demo.ngrok-free.app/report"
    assert report["api_schema"]["method"] == "POST"
    assert status["api_schema"]["url"] == "https://demo.ngrok-free.app/status"
    for tool in (report, status):
        assert tool["api_schema"]["request_headers"]["X-Lamplighter-Voice-Secret"] == {"secret_id": "sec-1"}
    # The caller is never asked for a phone number: it is a constant.
    assert report["api_schema"]["request_body_schema"]["properties"]["phone"]["constant_value"]
    assert status["api_schema"]["query_params_schema"]["properties"]["phone"]["constant_value"]
    assert "description" not in report["api_schema"]["request_body_schema"]["properties"]["phone"]


def test_first_run_creates_everything_and_never_sends_the_secret_in_tools():
    session = FakeSession()
    ids = configure(ElevenLabsClient("el-key-test", session), dict(ENV))
    assert ids == {
        "ELEVENLABS_VOICE_SECRET_ID": "sec-1",
        "ELEVENLABS_REPORT_TOOL_ID": "tool-report_light",
        "ELEVENLABS_STATUS_TOOL_ID": "tool-check_status",
        "ELEVENLABS_AGENT_ID": "agent-1",
    }
    agent_body = session.calls[-1][2]
    assert agent_body["conversation_config"]["agent"]["prompt"]["tool_ids"] == [
        "tool-report_light",
        "tool-check_status",
    ]
    assert "Lamplighter" in agent_body["conversation_config"]["agent"]["prompt"]["prompt"]
    # The voice secret is sent only to the secrets endpoint, never inside a tool or the agent.
    for method, path, body, headers in session.calls:
        assert headers == {"xi-api-key": "el-key-test"}
        if path != "/v1/convai/secrets":
            assert "voice-secret-value" not in json.dumps(body)


def test_rerun_updates_saved_ids_in_place():
    session = FakeSession()
    env = dict(ENV) | {
        "ELEVENLABS_VOICE_SECRET_ID": "sec-1",
        "ELEVENLABS_REPORT_TOOL_ID": "t-r",
        "ELEVENLABS_STATUS_TOOL_ID": "t-s",
        "ELEVENLABS_AGENT_ID": "a-1",
    }
    ids = configure(ElevenLabsClient("el-key-test", session), env)
    assert ids["ELEVENLABS_AGENT_ID"] == "a-1"
    assert [method for method, *_ in session.calls] == ["PATCH", "PATCH", "PATCH", "PATCH"]


def test_deleted_agent_is_recreated():
    session = FakeSession(missing={"/v1/convai/agents/gone"})
    ids = configure(ElevenLabsClient("el-key-test", session), dict(ENV) | {"ELEVENLABS_AGENT_ID": "gone"})
    assert ids["ELEVENLABS_AGENT_ID"] == "agent-1"


def test_api_errors_are_reported_without_the_key():
    class Failing(FakeSession):
        def request(self, method, url, headers, json, timeout):
            return FakeResponse(401, {"detail": "invalid api key"})

    with pytest.raises(setup_agent.SetupError) as error:
        configure(ElevenLabsClient("el-key-test", Failing()), dict(ENV))
    assert "401" in str(error.value)
    assert "el-key-test" not in str(error.value)
