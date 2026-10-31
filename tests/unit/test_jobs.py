from jobs.manager import Job, JobManager, RateLimiter


def test_rate_limiter_allows_ten_then_blocks():
    limiter = RateLimiter(limit=10, window_seconds=60)
    for _ in range(10):
        allowed, _ = limiter.allow("1.1.1.1")
        assert allowed
    allowed, retry_after = limiter.allow("1.1.1.1")
    assert allowed is False
    assert retry_after >= 1


def test_rate_limiter_is_per_key():
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("a")[0] is True
    assert limiter.allow("b")[0] is True
    assert limiter.allow("a")[0] is False


def test_job_positions_follow_submission_order():
    manager = JobManager(max_workers=5)
    positions = []
    for index in range(3):
        job = Job(job_id=f"j{index}", filing_id="f1", session_id="s1")
        positions.append(manager.create(job))
    assert positions == [1, 2, 3]


def test_job_update_and_get():
    manager = JobManager(max_workers=1)
    manager.create(Job(job_id="j1", filing_id="f1", session_id="s1"))
    manager.update("j1", state="parsing", progress=0.5, stage="parsing")
    job = manager.get("j1")
    assert job.state == "parsing"
    assert job.progress == 0.5
    assert manager.get("missing") is None
