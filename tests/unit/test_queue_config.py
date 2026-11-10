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
    crons = {p.task.name.split(":")[-1]: p.cron for p in app.periodic_registry.periodic_tasks.values()}
    assert crons["mnt.token_health"] == "0 2 * * *"
    assert crons["mnt.retention.oauth_pending_cleanup"] == "*/10 * * * *"
    assert {"mnt.retention.deletion_deadlines", "mnt.retention.purge_api_cache"} <= crons.keys()
    assert app.tasks[task_name("yt.upload")].queue == "youtube"
    assert crons["orch.reconcile"] == "*/2 * * * *"
    assert app.tasks[task_name("orch.reconcile")].queue == "orchestrator"


def test_research_jobs_run_on_the_agents_queue_and_trends_daily() -> None:
    app = build_app("postgresql://nobody@127.0.0.1:1/none")
    for name in ("research.discover", "research.blueprint", "research.keywords"):
        assert app.tasks[task_name(name)].queue == "agents"
    crons = {p.task.name.split(":")[-1]: p.cron for p in app.periodic_registry.periodic_tasks.values()}
    assert crons["a03.trend_scan"] == "0 1 * * *"  # 06:00 PKT
    assert crons["mnt.retention.purge_research_docs"] == "50 * * * *"
