import pytest

from fabric_agents.contracts import ROOT, load


@pytest.fixture
def config():
    return load(ROOT / "examples/loyalty/metadata.json")


@pytest.fixture
def snapshot():
    return load(ROOT / "examples/loyalty/snapshot-1.json")


@pytest.fixture
def updated():
    return load(ROOT / "examples/loyalty/snapshot-2.json")


@pytest.fixture
def standards():
    return load(ROOT / "standards/platform.json")

