"""Exercise state contracts through a real CLI process, including a restart."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "runtime" / "agent-02-smoke" / secrets.token_hex(6)
    output.mkdir(parents=True)
    token = secrets.token_hex(32)
    environment = {**os.environ, "TEST_ADMIN_TOKEN": token, "SIMULATOR_TOKEN": secrets.token_hex(32)}
    config_path = output / "config.yaml"
    config_path.write_text(json.dumps({"environment": "test", "storage_dir": str(output / "data"),
        "test_control_enabled": True, "otel_enabled": True, "otlp_enabled": False,
        "test_admin_token": "${TEST_ADMIN_TOKEN}", "simulator_token": "${SIMULATOR_TOKEN}"}), encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    command = [sys.executable, "main.py", "--config", str(config_path), "--host", "127.0.0.1", "--port", str(port)]

    def call(path, body=None, expected=200):
        request = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            assert response.code == expected, (path, response.code)
            result = json.load(response)
            if "request_id" in result and not path.startswith("/api/v1/observe/requests/"):
                assert result["request_id"] == response.headers["x-request-id"]
            return result

    def start(log):
        process = subprocess.Popen(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    call("/health")
                    return process
                except (URLError, TimeoutError):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("CLI failed to start; inspect server.log") from None
                    time.sleep(0.05)
        except BaseException:
            stop(process)
            raise

    def stop(process):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    with (output / "server.log").open("w", encoding="utf-8") as log:
        process = start(log)
        try:
            run = call("/api/test/v1/runs", {"name": "http-state-smoke"}, 201)
            path = "/api/test/v1/runs/" + run["test_run_id"]
            from state_helpers import run_report
            data = run_report(run, "events", {"events": [{"event_id": "secret-a", "fact": "smoke-secret-cache",
                                "observers": ["npc-a"], "actual_recipients": []}]}, entity_id=run["world_id"])
            accepted = call(path + "/reports", data)
            duplicate = call(path + "/reports", data)
            assert accepted["status"] == "accepted" and duplicate["status"] == "duplicate"
            a = call(path + "/npcs/npc-a/context")
            b = call(path + "/npcs/npc-b/context")
            assert "smoke-secret-cache" in json.dumps(a)
            assert "smoke-secret-cache" not in json.dumps(b)
            observation = call("/api/v1/observe/requests/" + a["request_id"])
            assert {s["stage"] for s in observation["stages"]} >= {"view_filter", "memory", "hooks", "model"}
            assert "smoke-secret-cache" not in json.dumps(observation)
            bad = run_report(run, "needs", {"hunger": 1.5}, expected_revision=1)
            assert call(path + "/reports", bad, 422)["reason"] == "invalid_payload"
        finally:
            stop(process)
        process = start(log)
        try:
            reopened = call(path + "/state")
            assert reopened["revision"] == 1
            assert call(path + "/reports", data)["status"] == "duplicate"
        finally:
            stop(process)
    evidence = {"base_url": base, "run": run, "accepted": accepted, "duplicate": duplicate,
                "secret_isolated": True, "restart_revision": reopened["revision"], "observation": observation,
                "shutdown": "both subprocesses stopped; pytest verifies graceful lifespan"}
    (output / "result.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(output / "result.json"), "secret_isolated": True, "restart_revision": 1}))


if __name__ == "__main__":
    main()
