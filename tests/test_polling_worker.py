from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock


from tests.conftest import dummy_protocol_config
from app.serial_io.serial_worker import POLLING_BOOT_GRACE, PollingWorker, SerialSettings
from app.decoder.types import PollingScheduleSpec


def _make_worker(
    schedules: list[PollingScheduleSpec],
    *,
    grace_expired: bool = True,
    parser_type: str = "framed",
) -> PollingWorker:
    """Build a worker with a mocked serial port, ready for run() in tests.

    Setting ``grace_expired=True`` (default) rewinds ``_open_time`` past the
    polling boot-grace window so tests don't have to sleep 2.5 s before the
    polling loop will actually emit anything.
    """
    settings = SerialSettings(port="COM_TEST", baud_rate=115200)
    pc = dummy_protocol_config(parser_type=parser_type)
    worker = PollingWorker(settings, pc, schedules)
    worker._serial = MagicMock()
    worker._serial.is_open = True
    worker._serial.in_waiting = 0
    worker._stop_event.clear()
    worker.start = MagicMock()  # never spawn a real QThread
    if grace_expired:
        worker._open_time = time.monotonic() - (POLLING_BOOT_GRACE + 1.0)
    worker.set_polling_global(True)
    return worker


def test_priority_tx_preempts_polling():
    """A priority TX in the queue runs before any polling fires."""
    sched = PollingScheduleSpec(target_id=0x100, interval_ms=10, timeout_ms=5)
    worker = _make_worker([sched])
    worker.enqueue_priority_tx(b"\xAA\xBB")

    fired = {"priority": False, "poll": False}

    def write(data):
        if data == b"\xAA\xBB":
            fired["priority"] = True
        else:
            fired["poll"] = True
        # Either way, exit the loop after one tick so the test terminates.
        worker._stop_event.set()

    worker._serial.write = write
    worker.run()

    assert fired["priority"], "priority TX must have been written"


def test_round_robin_cursor_visits_every_schedule():
    """All three schedules due at once must each fire in cursor order."""
    schedules = [
        PollingScheduleSpec(target_id=0x10, interval_ms=1000, timeout_ms=5),
        PollingScheduleSpec(target_id=0x20, interval_ms=1000, timeout_ms=5),
        PollingScheduleSpec(target_id=0x30, interval_ms=1000, timeout_ms=5),
    ]
    worker = _make_worker(schedules)

    # Force every schedule to be due immediately so the round-robin cursor
    # is the only thing controlling iteration order.
    for s in worker._schedules:
        s["next_run"] = 0.0

    poll_order: list[int] = []

    def fake_do_poll(sched: dict) -> None:
        poll_order.append(sched["spec"].target_id)
        if len(poll_order) >= 3:
            worker._stop_event.set()

    worker._do_poll = fake_do_poll  # type: ignore[assignment]
    worker.run()

    assert poll_order == [0x10, 0x20, 0x30], (
        f"cursor must visit each schedule in order; got {poll_order}"
    )


def test_disabled_schedule_is_skipped():
    """toggle_schedule(False) keeps the cursor advancing past that entry."""
    schedules = [
        PollingScheduleSpec(target_id=0x10, interval_ms=1000, timeout_ms=5),
        PollingScheduleSpec(target_id=0x20, interval_ms=1000, timeout_ms=5),
        PollingScheduleSpec(target_id=0x30, interval_ms=1000, timeout_ms=5),
    ]
    worker = _make_worker(schedules)
    worker.toggle_schedule(0x20, False)
    for s in worker._schedules:
        s["next_run"] = 0.0

    poll_order: list[int] = []

    def fake_do_poll(sched: dict) -> None:
        poll_order.append(sched["spec"].target_id)
        if len(poll_order) >= 2:
            worker._stop_event.set()

    worker._do_poll = fake_do_poll  # type: ignore[assignment]
    worker.run()

    assert 0x20 not in poll_order
    assert poll_order == [0x10, 0x30]


def test_toggle_reenable_resets_next_run_to_full_interval():
    """Re-enabling a disabled schedule waits a full interval before firing.

    Regression guard: prior behaviour left next_run at the long-past value
    from __init__, which made the first re-enabled poll fire immediately.
    Surprising for the user, especially right after a Pause.
    """
    sched = PollingScheduleSpec(target_id=0x55, interval_ms=250, timeout_ms=5)
    worker = _make_worker([sched])
    # Disable first so the toggle is a genuine transition.
    worker.toggle_schedule(0x55, False)
    # Backdate next_run so the test can prove the re-enable advanced it.
    worker._schedules[0]["next_run"] = 0.0

    before = time.monotonic()
    worker.toggle_schedule(0x55, True)
    after = time.monotonic()

    next_run = worker._schedules[0]["next_run"]
    # next_run should be (now + interval). Allow generous slack for clock
    # granularity on Windows.
    expected_low = before + 0.250 - 0.010
    expected_high = after + 0.250 + 0.050
    assert expected_low <= next_run <= expected_high, (
        f"next_run {next_run} should be ~{before + 0.250:.3f} (one interval ahead)"
    )


def test_disable_failed_schedule_marks_disabled_and_emits_once():
    """A build error disables the schedule and reports through error_occurred only once."""
    sched = PollingScheduleSpec(target_id=0x1234, interval_ms=10, timeout_ms=5)
    worker = _make_worker([sched])

    emitted: list[str] = []
    # PySide6 signals can be inspected but not patched directly; subscribe
    # via .connect on the underlying signal so the test can run without a
    # QApplication.
    worker.error_occurred.connect(lambda msg: emitted.append(msg))

    worker._disable_failed_schedule(worker._schedules[0], ValueError("won't fit"))
    worker._disable_failed_schedule(worker._schedules[0], ValueError("won't fit"))

    assert worker._schedules[0]["enabled"] is False
    assert worker._schedules[0].get("_failed_reported") is True
    assert len(emitted) == 1, f"expected one error emission, got {emitted}"
    assert "0x1234" in emitted[0]


def test_boot_grace_suppresses_polling_until_first_rx_or_timeout():
    """No polling fires within POLLING_BOOT_GRACE when zero RX has arrived."""
    sched = PollingScheduleSpec(target_id=0x77, interval_ms=1, timeout_ms=5)
    worker = _make_worker([sched], grace_expired=False)
    worker._open_time = time.monotonic()  # grace window just opened
    worker._rx_bytes = 0
    for s in worker._schedules:
        s["next_run"] = 0.0

    polled: list[Any] = []

    def fake_do_poll(sched: dict) -> None:
        polled.append(sched["spec"].target_id)
        worker._stop_event.set()

    worker._do_poll = fake_do_poll  # type: ignore[assignment]

    # Let the loop spin a few times within the boot-grace window.
    import threading
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    time.sleep(0.05)
    worker._stop_event.set()
    t.join(timeout=1.0)

    assert not polled, "polling should not fire during boot-grace before any RX"


def test_first_rx_byte_clears_boot_grace_immediately():
    """A device that responds quickly should NOT have to wait the full grace window."""
    sched = PollingScheduleSpec(target_id=0x99, interval_ms=1, timeout_ms=5)
    worker = _make_worker([sched], grace_expired=False)
    worker._open_time = time.monotonic()
    worker._rx_bytes = 5  # device already proved it's alive
    for s in worker._schedules:
        s["next_run"] = 0.0

    polled: list[int] = []

    def fake_do_poll(sched: dict) -> None:
        polled.append(sched["spec"].target_id)
        worker._stop_event.set()

    worker._do_poll = fake_do_poll  # type: ignore[assignment]
    worker.run()

    assert polled == [0x99]


def test_stop_event_exits_run_loop_promptly():
    """Setting stop_event mid-loop must end run() in well under the read timeout."""
    sched = PollingScheduleSpec(target_id=0x88, interval_ms=1000, timeout_ms=5)
    worker = _make_worker([sched])
    # Force "nothing to do" so the loop hits its idle sleep.
    for s in worker._schedules:
        s["enabled"] = False

    import threading
    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    time.sleep(0.02)
    start = time.monotonic()
    worker._stop_event.set()
    t.join(timeout=1.0)
    assert not t.is_alive(), "run() must exit after stop_event is set"
    assert time.monotonic() - start < 0.5, "stop must take well under the 2 s close() timeout"


def test_reset_metrics_zeroes_counters():
    """reset_metrics() clears the worker-owned counters and emits the new state."""
    sched = PollingScheduleSpec(target_id=0x10, interval_ms=10, timeout_ms=5)
    worker = _make_worker([sched])
    worker._timeouts = 3
    worker._crc_errors = 7
    worker._rx_bytes = 1024

    received: list[tuple[int, int, int]] = []
    worker.metrics_updated.connect(lambda t, c, r: received.append((t, c, r)))

    worker.reset_metrics()

    assert worker._timeouts == 0
    assert worker._crc_errors == 0
    assert worker._rx_bytes == 0
    assert received == [(0, 0, 0)], f"reset must emit one (0, 0, 0); got {received}"


def test_enqueue_priority_tx_emits_error_on_full_queue():
    """The 256-entry bounded queue refuses overflow rather than growing without limit."""
    sched = PollingScheduleSpec(target_id=0x10, interval_ms=10, timeout_ms=5)
    worker = _make_worker([sched])
    emitted: list[str] = []
    worker.warning_occurred.connect(lambda msg: emitted.append(msg))

    # The queue size is 256 (declared in PollingWorker.__init__). Push 257 to
    # force one overflow.
    for _i in range(256):
        worker.enqueue_priority_tx(b"x")
    worker.enqueue_priority_tx(b"x")  # the one that overflows

    assert worker._priority_tx_queue.full()
    assert len(emitted) == 1
    assert "TX queue full" in emitted[0]


def test_pipeline_depth_one_forces_sequential_mode():
    """Depth 1 must use the normal request/response polling path."""
    sched = PollingScheduleSpec(target_id=0x10, interval_ms=10, timeout_ms=5)
    worker = _make_worker([sched])

    worker.set_pipelining(True, depth=1)

    assert worker._pipelining_enabled is False
    assert worker._pipeline_depth == 1


def test_polling_start_flushes_stale_rx_and_parser_state():
    """Starting Auto-Fetch should not let old buffered frames satisfy the first poll."""
    sched = PollingScheduleSpec(target_id=0x10, interval_ms=10, timeout_ms=5)
    worker = _make_worker([sched])
    worker.set_polling_global(False)
    worker._parser.feed(b"\xAA\x55")
    worker._batch.append((object(), None))
    worker._in_flight.append({"target_id": 0x10, "tx_time": 1.0, "deadline": 2.0})
    worker._serial.reset_input_buffer = MagicMock()

    worker.set_polling_global(True)
    assert worker._flush_rx_before_polling is True

    worker._reset_rx_state_for_polling_start()

    worker._serial.reset_input_buffer.assert_called_once()
    assert worker._parser.buffered_bytes == 0
    assert worker._batch == []
    assert worker._in_flight == []


def test_polling_tx_gap_floor_overrides_fast_protocol_delay():
    """Polling uses the hardware-proven minimum gap even if config says 10 ms."""
    sched = PollingScheduleSpec(target_id=0x10, interval_ms=10, timeout_ms=5)
    worker = _make_worker([sched])

    assert worker._effective_tx_gap_ms(100) == 100
