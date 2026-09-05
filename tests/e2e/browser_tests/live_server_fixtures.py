"""
Shared fixture for true e2e tests: boots the real app as its own OS process
listening on a real TCP port, against a throwaway SQLite file DB, so tests
in this directory can drive it with genuine HTTP (or browser) traffic
instead of FastAPI's in-process TestClient.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Shared with tests that need to build their own verification/reset JWTs
# locally (e.g. an already-expired one) using the same secret the live
# server subprocess signs with - stateless JWTs don't need any server
# round-trip to construct, only a matching secret.
SECRET_KEY = "e2e-test-secret-key-not-for-production"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    db_path = REPO_ROOT / f"e2e_test_{uuid.uuid4().hex[:8]}.db"
    db_path.unlink(missing_ok=True)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "APP_ENV": "dev",     # triggers Base.metadata.create_all on startup
        "TESTING": "false",   # must NOT be "true", or startup DB setup is skipped
        "DATABASE_URL": f"sqlite+aiosqlite:///./{db_path.name}",
        "SECRET_KEY": SECRET_KEY,
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "SES_SOURCE_EMAIL": "test@example.com",
        "S3_BUCKET": "test-bucket",
        # So emailed links (e.g. verification) point back at this exact
        # server instead of the config default.
        "APP_BASE_URL": base_url,
    }

    log_fd, log_path = tempfile.mkstemp(prefix="e2e-server-", suffix=".log")
    log_file = os.fdopen(log_fd, "w")

    server_script = Path(__file__).resolve().parent / "_run_mocked_server.py"
    process = subprocess.Popen(
        [sys.executable, str(server_script), "127.0.0.1", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    try:
        deadline = time.monotonic() + 15
        healthy = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log_file.close()
                raise RuntimeError(
                    f"live server exited early (code {process.returncode}); log:\n"
                    + Path(log_path).read_text()
                )
            try:
                if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                    healthy = True
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.3)

        if not healthy:
            log_file.close()
            raise RuntimeError(
                "live server never became healthy within 15s; log:\n" + Path(log_path).read_text()
            )

        yield base_url, db_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if not log_file.closed:
            log_file.close()
        os.unlink(log_path)
        db_path.unlink(missing_ok=True)
