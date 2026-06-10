from typing import Any

default_prefix: str = "STM"
known_chains: dict[str, dict[str, Any]] = {
    "HIVE": {
        "chain_id": "beeab0de00000000000000000000000000000000000000000000000000000000",
        "min_version": "0.24.0",
        "prefix": "STM",
        "chain_assets": [
            {"asset": "@@000000013", "symbol": "HBD", "precision": 3, "id": 0},
            {"asset": "@@000000021", "symbol": "HIVE", "precision": 3, "id": 1},
            {"asset": "@@000000037", "symbol": "VESTS", "precision": 6, "id": 2},
        ],
    },
}
