"""Isolated, loopback-only browser acceptance backend; no .env loading."""
import tempfile
import os
from pathlib import Path

import uvicorn

from core.config.schemas import AppConfig
from server import create_app


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='bigfish-e2e-') as directory:
        uvicorn.run(create_app(AppConfig(environment='test', storage_dir=Path(directory),
            test_control_enabled=True, test_admin_token='e2e-admin', otel_enabled=False)),
            host='127.0.0.1', port=int(os.environ.get('BIGFISH_E2E_API_PORT', '8092')), access_log=False)
