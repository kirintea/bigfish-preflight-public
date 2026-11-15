"""Run a real CLI server, query a correlated health trace, then stop the process."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def main():
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "runtime" / "agent-01-smoke"
    output_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    environment = {**os.environ, "TEST_ADMIN_TOKEN": token, "SIMULATOR_TOKEN": secrets.token_hex(32)}
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 8091))
            port = 8091
        except OSError:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
    command = [sys.executable, "main.py", "--config", "configs/test.yaml", "--host", "127.0.0.1", "--port", str(port)]
    base = f"http://127.0.0.1:{port}"
    with (output_dir / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(f"{base}/health", timeout=1) as response:
                        health = json.load(response)
                        assert response.status == 200
                    break
                except (URLError, TimeoutError):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("CLI service failed to start; see smoke server.log") from None
                    time.sleep(0.05)
            request = Request(f"{base}/api/v1/observe/requests/{health['request_id']}",
                              headers={"Authorization": f"Bearer {token}"})
            with urlopen(request, timeout=2) as response:
                observed = json.load(response)
            assert observed["trace_id"] == health["trace_id"]
            assert observed["stages"][-1]["stage"] == "request"
            assert observed["stages"][-1]["status"] == "ok"
            assert {item["stage"] for item in observed["stages"]} == {"request", "health"}
            evidence = {"base_url": base, "health": health, "observation": observed,
                        "shutdown": "subprocess terminated after HTTP smoke; graceful lifespan verified by pytest"}
            (output_dir / "result.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(evidence, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
