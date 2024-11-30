from typing import Any


def deep_get(dictionary: dict[Any, Any], *path: Any, default: Any = None) -> Any:
    current_value = dictionary
    for key in path:
        if current_value is None or key not in current_value:
            return default
        current_value = current_value[key]
    return current_value
