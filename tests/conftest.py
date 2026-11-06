"""Fixtures partagées."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Charge custom_components/energy_priority."""
    yield
