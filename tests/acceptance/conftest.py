"""Acceptance tests reuse the system-test harness: the real app, the real
config, a simulated BMS over a real transport."""

from tests.system.conftest import device, error_boxes, qapp, window  # noqa: F401  (fixtures)
