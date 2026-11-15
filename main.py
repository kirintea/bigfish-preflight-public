import argparse

import uvicorn

from core.config.manager import ConfigManager
from server import create_app


def main():
    parser = argparse.ArgumentParser(description="Bigfish Agent service")
    parser.add_argument("--config", default="configs/dev.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    config = ConfigManager().load(args.config)
    uvicorn.run(create_app(config), host=args.host, port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
