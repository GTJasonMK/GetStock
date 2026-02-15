from app.tasks import scheduler as scheduler_module


def test_init_scheduler_default_jobs_have_expected_triggers():
    scheduler_module.scheduler.remove_all_jobs()
    scheduler_module.init_scheduler()

    daily_job = scheduler_module.scheduler.get_job("daily_refresh")
    assert daily_job is not None
    assert "day_of_week='mon-fri'" in str(daily_job.trigger)
    assert "hour='9'" in str(daily_job.trigger)
    assert "minute='0'" in str(daily_job.trigger)

    realtime_job = scheduler_module.scheduler.get_job("realtime_refresh")
    assert realtime_job is not None
    assert "day_of_week='mon-fri'" in str(realtime_job.trigger)
    assert "hour='9-11,13-15'" in str(realtime_job.trigger)
    assert "minute='*/5'" in str(realtime_job.trigger)

