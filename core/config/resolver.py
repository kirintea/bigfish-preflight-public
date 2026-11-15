"""Resolve environment placeholders recursively in configuration values."""

import os
import re


class EnvVarResolver:
    _PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")

    @classmethod
    def resolve(cls, obj, env_mapping=None):
        if isinstance(obj, dict):
            return {key: cls.resolve(value, env_mapping) for key, value in obj.items()}
        if isinstance(obj, list):
            return [cls.resolve(value, env_mapping) for value in obj]
        if not isinstance(obj, str):
            return obj

        def replace(match):
            name, default = match.groups()
            value = (env_mapping or {}).get(name, os.getenv(name))
            if value is not None:
                return value
            if default is not None:
                return default
            raise RuntimeError(f"Unresolved environment variable: {name}")

        return cls._PATTERN.sub(replace, obj)
