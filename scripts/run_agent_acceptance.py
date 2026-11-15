from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", default="runtime/acceptance/latest.json")
    args = parser.parse_args()
    checks = [
        ("backend_tests", ["tests/test_save_roundtrip.py", "tests/test_restore_epoch.py", "tests/test_recovery_references.py"]),
        ("memory_tests", ["tests/test_memory_ownership.py", "tests/test_memory_compression.py"]),
        ("conversation_tests", ["tests/test_conversation_identity.py", "tests/test_conversations_api.py"]),
    ]
    results = []
    for name, paths in checks:
        command = [sys.executable, "-m", "pytest", *paths, "-q"]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        results.append({"name": name, "status": "passed" if completed.returncode == 0 else "failed",
                        "exit_code": completed.returncode, "output_tail": completed.stdout[-1000:]})
    payload = {"mode": "offline" if args.offline else "default", "created_at": datetime.now(timezone.utc).isoformat(),
               "checks": results, "passed": all(item["status"] == "passed" for item in results),
               "real_model": "skipped", "external_otel": "not_run"}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
