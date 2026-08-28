from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_uv_daemon_stdout_is_pure_jsonl(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")

    env = os.environ.copy()
    env["MARKET_SENTINEL_DATA_DIR"] = str(tmp_path)
    proc = subprocess.Popen(
        [
            uv,
            "run",
            "--directory",
            str(REPO),
            "market-sentinel",
            "--provider",
            "fake",
            "daemon",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(REPO),
        env=env,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None
    try:
        script = [
            {"protocol_version": 1, "type": "hello", "request_id": "h1", "host": "pytest"},
            {"protocol_version": 1, "type": "get_state", "request_id": "g1"},
            {"protocol_version": 1, "type": "shutdown", "request_id": "x1"},
        ]
        for message in script:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
        stdout_text, stderr_text = proc.communicate(timeout=30)
    except Exception:
        proc.kill()
        proc.wait(timeout=5)
        raise

    assert proc.returncode == 0, stderr_text
    lines = [line for line in stdout_text.splitlines() if line.strip()]
    assert lines, f"empty stdout; stderr={stderr_text!r}"
    decoded = []
    for line in lines:
        payload = json.loads(line)
        assert payload["protocol_version"] == 1
        decoded.append(payload)
    types = [item["type"] for item in decoded]
    assert types[0] == "ready"
    assert "state" in types
    assert types[-1] == "shutdown_ack"
    assert "Resolved" not in stdout_text
    assert "INFO" not in stdout_text
    assert "event_generated" not in stdout_text
    assert "alert_presented" not in stdout_text
