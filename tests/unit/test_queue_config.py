from __future__ import annotations

from tubeforge.queue import HEAVY_QUEUES, LIGHT_QUEUES, WORKER_PROFILES, build_app, task_name


def test_profiles_match_architecture() -> None:
    assert WORKER_PROFILES["heavy"] == (("heavy",), 1)  # one heavy job at a time (H-LITE)
    assert set(LIGHT_QUEUES) == {"orchestrator", "agents", "youtube", "notify", "maintenance"}
    assert not set(LIGHT_QUEUES) & set(HEAVY_QUEUES)


def test_tasks_registered_on_expected_queues() -> None:
    app = build_app("postgresql://nobody@127.0.0.1:1/none")  # no connection is opened
    assert app.tasks[task_name("mnt.ping")].queue == "maintenance"
    assert app.tasks[task_name("heavy.ping")].queue == "heavy"
