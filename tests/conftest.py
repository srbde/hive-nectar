"""Test configuration ensuring local sources are importable."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if SRC_PATH.exists():
    sys.path.insert(0, str(SRC_PATH))


_TEST_HOME: Path | None = None


def pytest_configure(config):
    global _TEST_HOME
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    _TEST_HOME = Path(tempfile.mkdtemp(prefix=f"hive-nectar-{worker}-"))

    # The wallet/config stores use appdirs, which normally resolves under the
    # real HOME. Parallel workers must not share that SQLite file.
    os.environ["HOME"] = str(_TEST_HOME)
    os.environ["XDG_DATA_HOME"] = str(_TEST_HOME / ".local" / "share")
    os.environ["XDG_CONFIG_HOME"] = str(_TEST_HOME / ".config")
    os.environ["XDG_CACHE_HOME"] = str(_TEST_HOME / ".cache")


def pytest_unconfigure(config):
    if _TEST_HOME is not None:
        shutil.rmtree(_TEST_HOME, ignore_errors=True)


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
