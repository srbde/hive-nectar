"""Test configuration ensuring local sources are importable and sandboxed."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

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
