import json
import os
from pathlib import Path
from typing import Any, Optional

from astrbot.api import logger


def unwrap_config_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return getattr(value, "value")
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def is_empty_config_value(value: Any) -> bool:
    return value is None or str(value).strip() in {"", "None", "null"}


def iter_config_items(config: Any):
    if isinstance(config, dict):
        yield from config.items()
        return

    if hasattr(config, "keys") and hasattr(config, "__getitem__"):
        try:
            for key in config.keys():
                yield key, config[key]
            return
        except Exception:
            pass

    if hasattr(config, "__dict__"):
        yield from vars(config).items()


def search_config_value(config: Any, keys: list[str], visited: Optional[set[int]] = None) -> Any:
    if config is None:
        return None

    if visited is None:
        visited = set()

    config_id = id(config)
    if config_id in visited:
        return None
    visited.add(config_id)

    wanted = {key.lower() for key in keys}

    for key, value in iter_config_items(config):
        if str(key).lower() in wanted:
            value = unwrap_config_value(value)
            if not is_empty_config_value(value):
                return value

    for _, value in iter_config_items(config):
        value = unwrap_config_value(value)
        if isinstance(value, (dict, list, tuple)) or hasattr(value, "__dict__"):
            found = search_config_value(value, keys, visited)
            if not is_empty_config_value(found):
                return found

    if isinstance(config, (list, tuple)):
        for item in config:
            found = search_config_value(item, keys, visited)
            if not is_empty_config_value(found):
                return found

    return None


def load_json_config(file_name: str) -> dict[str, Any]:
    config_path = Path(__file__).resolve().parents[1] / file_name
    if not config_path.exists():
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
            if isinstance(data, dict):
                logger.info(f"[Config] 已加载本地配置文件: {config_path.name}")
                return data
    except Exception as exc:
        logger.warning(f"[Config] 读取本地配置文件失败 ({file_name}): {exc}")
    return {}


def config_get(configs: list[Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        env_value = os.getenv(key)
        if not is_empty_config_value(env_value):
            return env_value

    for config in configs:
        value = search_config_value(config, keys)
        if not is_empty_config_value(value):
            return value

    return default


def config_str(configs: list[Any], keys: list[str], default: str = "") -> str:
    return str(config_get(configs, keys, default))


def config_int(configs: list[Any], keys: list[str], default: int) -> int:
    try:
        return int(config_get(configs, keys, default))
    except (TypeError, ValueError):
        return default


def config_float(configs: list[Any], keys: list[str], default: float) -> float:
    try:
        return float(config_get(configs, keys, default))
    except (TypeError, ValueError):
        return default