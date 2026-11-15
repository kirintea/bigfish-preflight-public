"""Loopback development server with isolated storage and no .env loading."""
import argparse
from pathlib import Path
from secrets import token_urlsafe

import uvicorn

from core.config.schemas import AppConfig
from server import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8091)
    parser.add_argument('--storage', type=Path, default=Path('runtime/agent-03-local'))
    parser.add_argument('--admin-token', default=None)
    args = parser.parse_args()
    token = args.admin_token or token_urlsafe(24)
    print(f'Local NPC LAB credential: {token}', flush=True)
    uvicorn.run(create_app(AppConfig(environment='development', storage_dir=args.storage,
        test_control_enabled=True, test_admin_token=token, otel_enabled=True)),
        host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main()
