"""Test configuration for legacy integration tests."""

import sys
import time
from pathlib import Path

import httpcore2
import httpx2
import pytest

# Alias httpx/httpcore for VCR compatibility
sys.modules["httpcore"] = httpcore2
sys.modules["httpx"] = httpx2

# Monkeypatch httpx2 connection limits to prevent connection pool exhaustion hangs/deadlocks under VCR.py
original_client_init = httpx2.Client.__init__


def patched_client_init(self, *args, **kwargs):
    kwargs["limits"] = httpx2.Limits(max_connections=None, max_keepalive_connections=None)
    original_client_init(self, *args, **kwargs)


httpx2.Client.__init__ = patched_client_init

# Monkeypatch time.sleep to cap sleep duration to 0.001s for fast test execution
original_sleep = time.sleep


def patched_sleep(seconds):
    original_sleep(min(seconds, 0.001))


time.sleep = patched_sleep


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
        "nectargraphenebase",
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
                item.add_marker(pytest.mark.vcr)


@pytest.fixture(scope="session")
def vcr_config():
    return {
        "match_on": ["method", "scheme", "host", "port", "path", "query", "json_rpc_body"],
        "allow_playback_repeats": True,
    }


def json_rpc_body_matcher(r1, r2):
    import json

    try:
        body1 = json.loads(r1.body.decode("utf-8"))
        body2 = json.loads(r2.body.decode("utf-8"))
        if isinstance(body1, dict) and isinstance(body2, dict):
            body1.pop("id", None)
            body2.pop("id", None)
            return body1 == body2
        elif isinstance(body1, list) and isinstance(body2, list):
            for b in body1:
                if isinstance(b, dict):
                    b.pop("id", None)
            for b in body2:
                if isinstance(b, dict):
                    b.pop("id", None)
            return body1 == body2
    except Exception:
        pass
    return r1.body == r2.body


def pytest_recording_configure(config, vcr):
    vcr.register_matcher("json_rpc_body", json_rpc_body_matcher)
