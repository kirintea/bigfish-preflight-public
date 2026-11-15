"""Opt-in live probe; add --llm for one billed model request.

One short LLM request, no retries. Secrets and model content are never printed.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config.schemas import AppConfig
from server import create_app


def main():
    parser = argparse.ArgumentParser(description="Local collector/Jaeger and optional real LLM probe")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--otel-endpoint", default="http://127.0.0.1:4317")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    values = dotenv_values(root / ".env")
    result = {"llm": {"attempts": 0}, "otel": {"received_in_jaeger": False}}
    directory = root / "runtime" / "integration-probe" / uuid4().hex
    endpoint = args.otel_endpoint
    parsed_endpoint = urlsplit(endpoint if "://" in endpoint else "http://" + endpoint)
    if parsed_endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
        result["otel"]["error"] = "configured_collector_is_not_local"
    else:
        admin_token = uuid4().hex
        config = AppConfig(storage_dir=directory, otlp_enabled=True, otlp_endpoint=endpoint,
                           offline_mode=True, test_control_enabled=True, test_admin_token=admin_token,
                           service_name="bigfish-agent", shutdown_timeout_seconds=5)
        try:
            with TestClient(create_app(config)) as client:
                client.headers["Authorization"] = f"Bearer {admin_token}"
                created = client.post("/api/test/v1/runs", json={"name": "OTel agent probe"})
                created.raise_for_status()
                run_id = created.json()["test_run_id"]
                response = client.post(f"/api/test/v1/runs/{run_id}/conversations/probe/turns",
                    json={"turn_id": "probe-turn", "text": "hello", "allow_fallback": False})
                response.raise_for_status()
                trace_id = response.headers["x-trace-id"]
                result["otel"]["trace_id"] = trace_id
                result["otel"]["request_id"] = response.headers["x-request-id"]
                result["otel"]["flushed"] = client.app.state.tracing.force_flush(5)
                result["otel"]["status"] = client.app.state.events.status()
                with httpx.Client(timeout=5, trust_env=False) as http:
                    deadline = time.monotonic() + 15
                    while True:
                        lookup = http.get(f"http://127.0.0.1:16686/api/traces/{trace_id}")
                        payload = lookup.json() if lookup.status_code == 200 else {}
                        traces = payload.get("data") or []
                        matching = [item for item in traces if item.get("traceID") == trace_id]
                        if matching:
                            spans = matching[0].get("spans", [])
                            names = sorted(span["operationName"] for span in spans)
                            result["otel"]["operations"] = names
                            turn_spans = [span for span in spans if span["operationName"].startswith("invoke_agent ")]
                            model_spans = [span for span in spans if span["operationName"].startswith("chat ")]
                            parent_ok = bool(turn_spans and model_spans
                                and all(span["operationName"].startswith(("invoke_agent ", "chat ", "execute_tool "))
                                        for span in spans)
                                and any(ref.get("spanID") == turn_spans[0]["spanID"]
                                        for ref in model_spans[0].get("references", [])))
                            result["otel"]["parent_child_verified"] = parent_ok
                            result["otel"]["received_in_jaeger"] = parent_ok
                            break
                        if time.monotonic() >= deadline:
                            result["otel"]["error"] = "trace_not_found_before_deadline"
                            break
                        time.sleep(0.25)
        except Exception as exc:
            result["otel"]["error_type"] = type(exc).__name__

    key, base, model = (values.get(name) for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"))
    if not args.llm:
        result["llm"]["skipped"] = True
    elif not all((key, base, model)):
        result["llm"]["error"] = "missing_configuration"
    else:
        parsed = urlsplit(base)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            result["llm"]["error"] = "invalid_endpoint"
        else:
            result["llm"]["attempts"] = 1
            started = time.monotonic()
            try:
                with httpx.Client(timeout=30, follow_redirects=False) as http:
                    response = http.post(base.rstrip("/") + "/chat/completions", headers={
                        "Authorization": f"Bearer {key}",
                    }, json={"model": model, "messages": [{"role": "user", "content": "Reply only OK."}],
                             "max_tokens": 16, "stream": False})
                result["llm"]["http_status"] = response.status_code
                if response.is_success:
                    body = response.json()
                    content = body.get("choices", [{}])[0].get("message", {}).get("content")
                    result["llm"]["nonempty_reply"] = isinstance(content, str) and bool(content.strip())
                    usage = body.get("usage", {})
                    result["llm"]["usage"] = {name: usage[name] for name in
                        ("prompt_tokens", "completion_tokens", "total_tokens") if isinstance(usage.get(name), int)}
                else:
                    result["llm"]["error"] = "provider_rejected_request"
            except Exception as exc:
                result["llm"]["error_type"] = type(exc).__name__
            result["llm"]["duration_ms"] = round((time.monotonic() - started) * 1000)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["otel"].get("received_in_jaeger") and (not args.llm or result["llm"].get("nonempty_reply")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
