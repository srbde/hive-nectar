"""Test configuration ensuring local sources are importable."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if SRC_PATH.exists():
    sys.path.insert(0, str(SRC_PATH))


def pytest_collection_modifyitems(config, items):
    offline_files = {
        "test_aes.py",
        "test_asciichart.py",
        "test_objectcache.py",
        "test_profile.py",
        "test_utils.py",
        "test_haf.py",
        "test_add_basic.py",
        "test_asset_serialization.py",
        "test_ec_basic.py",
        "test_tweak_add.py",
        "test_openapi_rpcutils.py",
        "test_shared_instance.py",
        "test_node.py",
        "test_openapi_map.py",
        "test_rpcutils.py",
    }

    offline_dirs = {
        "nectarbase",
        "nectargraphene",
        "nectarstorage",
    }

    for item in items:
        module_path = item.fspath
        if module_path:
            path_parts = Path(module_path).parts
            filename = Path(module_path).name

            is_offline = filename in offline_files or any(
                part in offline_dirs for part in path_parts
            )

            if not is_offline:
                item.add_marker(pytest.mark.network)
