"""Load and validate application configuration with field-only errors."""

import os

from pydantic import ValidationError

from .loader import YamlLoader
from .schemas import AppConfig


class ConfigManager:
    def load(self, path=None):
        path = path or f"configs/{os.getenv('APP_ENV', 'dev')}.yaml"
        try:
            return AppConfig.model_validate(YamlLoader.load(path))
        except ValidationError as exc:
            fields = [".".join(map(str, item["loc"])) or "<root>" for item in exc.errors()]
            raise RuntimeError(f"Invalid configuration {path}; fields: {', '.join(fields)}") from None
