from app.tasks import scheduler as scheduler_module


def test_schedule_ai_analysis_job_id_uses_normalized_stock_code(monkeypatch):
    scheduler_module.scheduler.remove_all_jobs()
    monkeypatch.setattr(scheduler_module, "is_scheduler_leader", lambda: True)

    job_id_1 = scheduler_module.schedule_ai_analysis(
        stock_code="SH600000",
        cron_expression="0 15 * * 1-5",
        prompt_template=None,
    )
    assert job_id_1 == "ai_analysis_sh600000"
    assert scheduler_module.scheduler.get_job("ai_analysis_sh600000") is not None

    job_id_2 = scheduler_module.schedule_ai_analysis(
        stock_code="sh600000",
        cron_expression="0 15 * * 1-5",
        prompt_template=None,
    )
    assert job_id_2 == "ai_analysis_sh600000"
    assert len(scheduler_module.scheduler.get_jobs()) == 1

