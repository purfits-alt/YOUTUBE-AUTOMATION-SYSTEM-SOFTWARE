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


def test_token_health_runs_daily_on_maintenance() -> None:
    app = build_app("postgresql://nobody@127.0.0.1:1/none")
    task = app.tasks[task_name("mnt.token_health")]
    assert task.queue == "maintenance"
    crons = [p.cron for p in app.periodic_registry.periodic_tasks.values()]
    assert "0 2 * * *" in crons
