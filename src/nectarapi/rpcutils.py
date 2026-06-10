import json
import logging
from collections.abc import Iterable
from typing import Any

log = logging.getLogger(__name__)


def get_query(
    request_id: int,
    api_name: str,
    name: str,
    args: dict[str, Any] | Iterable[Any] | Any,
) -> dict[str, Any] | list[dict[str, Any]]:
    """
    Build an appbase-style JSON-RPC request payload.

    Always emits the `api.method` form (no condenser `call` indirection). Supports:
    - Single dict params
    - Positional params passed as an iterable
    - Batch creation when provided a list of dicts inside an iterable
    """
    normalized_args: Any
    # Convert tuples to lists for easier inspection
    if isinstance(args, tuple):
        normalized_args = list(args)
    else:
        normalized_args = args

    # Pass through plain dict
    if isinstance(normalized_args, dict):
        params: dict[str, Any] | list[Any] = json.loads(json.dumps(normalized_args))
        return {
            "method": f"{api_name}.{name}",
            "params": params,
            "jsonrpc": "2.0",
            "id": request_id,
        }

    if isinstance(normalized_args, list) and normalized_args:
        # Batch: list of dicts directly
        if len(normalized_args) > 1 and all(isinstance(item, dict) for item in normalized_args):
            queries: list[dict[str, Any]] = []
            for entry in normalized_args:
                queries.append(
                    {
                        "method": f"{api_name}.{name}",
                        "params": json.loads(json.dumps(entry)),
                        "jsonrpc": "2.0",
                        "id": request_id,
                    }
                )
                request_id += 1
            return queries

        # Batch: list of dicts nested inside a single element
        if (
            len(normalized_args) == 1
            and isinstance(normalized_args[0], list)
            and normalized_args[0]
            and all(isinstance(item, dict) for item in normalized_args[0])
        ):
            queries: list[dict[str, Any]] = []
            for entry in normalized_args[0]:
                queries.append(
                    {
                        "method": f"{api_name}.{name}",
                        "params": json.loads(json.dumps(entry)),
                        "jsonrpc": "2.0",
                        "id": request_id,
                    }
                )
                request_id += 1
            return queries

        # Single dict wrapped in a list
        if len(normalized_args) == 1 and isinstance(normalized_args[0], dict):
            return {
                "method": f"{api_name}.{name}",
                "params": json.loads(json.dumps(normalized_args[0])),
                "jsonrpc": "2.0",
                "id": request_id,
            }

        # Generic positional args
        return {
            "method": f"{api_name}.{name}",
            "params": json.loads(json.dumps(normalized_args)),
            "jsonrpc": "2.0",
            "id": request_id,
        }

    # Fallback: empty params (use list to satisfy condenser/appbase empty-arg methods)
    return {
        "method": f"{api_name}.{name}",
        "jsonrpc": "2.0",
        "params": [] if api_name == "condenser_api" else {},
        "id": request_id,
    }
