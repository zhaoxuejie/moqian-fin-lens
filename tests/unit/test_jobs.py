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


def test_job_is_done_only_after_success_callback():
    """客户端轮询到 done 时，保存会话的回调必须已经跑完。"""
    import threading

    manager = JobManager(max_workers=1)
    manager.create(Job(job_id="j1", filing_id="f1", session_id="s1"))
    entered, release = threading.Event(), threading.Event()
    states_during_save = []

    def on_success(_result):
        entered.set()
        release.wait(5)
        states_during_save.append(manager.get("j1").state)

    manager.submit("j1", lambda progress: "ok", on_success, lambda exc: None)
    assert entered.wait(5)
    assert manager.get("j1").state != "done"
    release.set()
    for _ in range(100):
        if manager.get("j1").state == "done":
            break
        threading.Event().wait(0.05)
    assert manager.get("j1").state == "done"
    assert states_during_save == ["parsing"]


def test_job_fails_when_success_callback_fails():
    import threading

    manager = JobManager(max_workers=1)
    manager.create(Job(job_id="j1", filing_id="f1", session_id="s1"))
    errors = []
    finished = threading.Event()

    def on_error(exc):
        errors.append(exc)
        finished.set()

    def on_success(_result):
        raise RuntimeError("disk full")

    manager.submit("j1", lambda progress: "ok", on_success, on_error)
    assert finished.wait(5)
    job = manager.get("j1")
    assert job.state == "failed"
    assert job.error["stage"] == "persist"
    assert manager.active == 0
