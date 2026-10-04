"""Exercise user controls and error states without a browser or network."""

from streamlit.testing.v1 import AppTest

from config import ROOT_DIR
from dashboard import data


def test_preview_controls_search_and_reset() -> None:
    app = AppTest.from_file(ROOT_DIR / "dashboard/app.py", default_timeout=30).run()
    assert not app.exception
    app.selectbox(key="policy").select("fifo").run()
    app.slider(key="budget").set_value(80).run()
    assert not app.exception
    app.text_input[0].set_value("no-such-ticket").run()
    assert any("No matching reports" in item.value for item in app.markdown)
    app.button(key="reset-settings").click().run()
    assert app.selectbox(key="policy").value == "tuned"
    assert app.slider(key="budget").value == 100
    assert not app.exception


def test_live_failure_has_no_fake_live_queue(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise data.DataUnavailable("Service unavailable")

    monkeypatch.setattr(data, "fetch_live", unavailable)
    app = AppTest.from_file(ROOT_DIR / "dashboard/app.py", default_timeout=30).run()
    app.selectbox(key="source").select("Live dispatch").run()
    assert not app.exception
    assert app.warning
    assert any("Dispatch data is unavailable" in item.value for item in app.markdown)


def test_live_disconnect_preserves_only_the_same_scenario(monkeypatch) -> None:
    state = {"offline": False}

    def live(base_url, policy, budget, token):
        if state["offline"]:
            raise data.DataUnavailable("Connection lost")
        return data.load_preview(policy, budget)

    monkeypatch.setattr(data, "fetch_live", live)
    app = AppTest.from_file(ROOT_DIR / "dashboard/app.py", default_timeout=30).run()
    app.selectbox(key="source").select("Live dispatch").run()
    state["offline"] = True
    app.run()
    assert not app.exception
    assert any("Connection lost · saved view" in item.value for item in app.markdown)
    app.slider(key="budget").set_value(80).run()
    assert any("Dispatch data is unavailable" in item.value for item in app.markdown)
    assert not any("Connection lost · saved view" in item.value for item in app.markdown)


def test_empty_live_queue_renders_without_crashing(monkeypatch) -> None:
    view = data.load_preview("tuned", 100)
    view.queue = []
    view.plan.queue = []
    view.plan.lights_planned = 0
    view.plan.skipped_count = 0
    view.plan.minutes_used = 0
    view.plan.note = "No repairs are currently queued."
    view.baseline = view.plan.model_copy(deep=True)
    monkeypatch.setattr(data, "fetch_live", lambda *args: view)
    app = AppTest.from_file(ROOT_DIR / "dashboard/app.py", default_timeout=30).run()
    app.selectbox(key="source").select("Live dispatch").run()
    assert not app.exception
    assert any("No lights in this view" in item.value for item in app.markdown)


def test_ticket_details_and_evaluation_are_separate_workspaces():
    app = AppTest.from_file(ROOT_DIR / "dashboard/app.py", default_timeout=30).run()
    ticket = data.load_preview("tuned", 100).queue[0].ticket_id
    app.selectbox(key="selected_ticket").select(ticket).run()
    assert not app.exception
    assert any("Why this light ranks here" in item.value for item in app.markdown)
    app.radio(key="workspace").set_value("Evaluation").run()
    assert app.info
    assert not any(box.key == "selected_ticket" for box in app.selectbox)
    assert not app.exception


def test_new_revision_invalidates_review_and_prevents_confirm(monkeypatch):
    state = {"revision": 1}

    def live(*args):
        view = data.load_preview("tuned", 100)
        view.revision = state["revision"]
        view.plan.candidate_id = "test-candidate-123456"
        return view

    monkeypatch.setenv("DISPATCH_SHARED_SECRET", "test-token")
    monkeypatch.setattr(data, "fetch_live", live)
    app = AppTest.from_file(ROOT_DIR / "dashboard/app.py", default_timeout=30).run()
    app.selectbox(key="source").select("Live dispatch").run()
    app.button(key="review-plan").click().run()
    app.checkbox(key="review_ack").check().run()
    assert not app.button(key="confirm-plan").disabled
    state["revision"] = 2
    app.run()
    assert not any(button.key == "confirm-plan" for button in app.button)
    assert not app.exception
