"""Shared fixtures."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    yield


@pytest.fixture
def expected_lingering_timers() -> bool:
    """The MQTT integration keeps a periodic misc timer running after teardown."""
    return True
