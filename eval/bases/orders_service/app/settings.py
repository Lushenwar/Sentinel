import json
import os
from pathlib import Path

_CONFIG = json.loads((Path(__file__).parent.parent / "config.json").read_text())


def get(section: str, key: str):
    """Config value, overridable by ORDERS_<SECTION>_<KEY> in the environment."""
    env_key = f"ORDERS_{section.upper()}_{key.upper()}"
    if env_key in os.environ:
        return json.loads(os.environ[env_key])
    return _CONFIG[section][key]
