from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


TESTS_ROOT = Path(__file__).resolve().parent
XDEBUG_ROOT = TESTS_ROOT.parent
REPO_ROOT = XDEBUG_ROOT.parent

if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("xdebug")
    group.addoption(
        "--xdebug-bin",
        default=os.environ.get("XDEBUG_BIN", str(REPO_ROOT / "tools" / "xdebug")),
        help="xdebug wrapper/binary path",
    )
    group.addoption(
        "--xdebug-artifacts",
        default=os.environ.get(
            "XDEBUG_TEST_ARTIFACTS",
            str(XDEBUG_ROOT / "tests" / "artifacts"),
        ),
        help="failure artifact root",
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def xdebug_root() -> Path:
    return XDEBUG_ROOT


@pytest.fixture(scope="session")
def xdebug_bin(pytestconfig: pytest.Config) -> Path:
    return Path(pytestconfig.getoption("--xdebug-bin")).expanduser().resolve()


@pytest.fixture(scope="session")
def artifact_root(pytestconfig: pytest.Config) -> Path:
    return Path(pytestconfig.getoption("--xdebug-artifacts")).expanduser().resolve()


@pytest.fixture
def isolated_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home
