import json

from ops.runlog import append_run, should_alert, success_rate


def test_append_run_writes_json_line(tmp_path):
    log = tmp_path / "logs" / "runs.jsonl"
    append_run(log, {"session_id": "s1", "pages": 10, "ok": True})
    append_run(log, {"session_id": "s2", "pages": 20, "ok": False})

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["session_id"] == "s1"
    assert first["ts"]
    assert json.loads(lines[1])["ok"] is False


def test_append_run_rotates_when_large(tmp_path):
    log = tmp_path / "runs.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("x" * (5 * 1024 * 1024 + 10), encoding="utf-8")

    append_run(log, {"session_id": "s3"})

    assert (tmp_path / "runs.jsonl.1").exists()
    assert log.read_text(encoding="utf-8").count("\n") == 1


def test_success_rate_and_alert_threshold():
    assert success_rate(10, 0) == 1.0
    assert success_rate(10, 2) == 0.8
    assert should_alert(9, 1) is False
    assert should_alert(10, 2) is True
    assert should_alert(9, 9) is False
