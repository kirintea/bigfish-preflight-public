"""Load YAML configuration and resolve environment placeholders."""

from pathlib import Path

import yaml

from .resolver import EnvVarResolver


class YamlLoader:
    @staticmethod
    def load(file_path):
        with Path(file_path).open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("Configuration must be a mapping")
        return EnvVarResolver.resolve(raw)
