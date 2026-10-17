"""The helper process that runs segment finishing off the GUI's GIL."""

from __future__ import annotations

import os

import pytest

from app.serial_logging import _isolated


def _pid() -> int:
    return os.getpid()


def _boom() -> None:
    raise ValueError("bad input")


@pytest.fixture(autouse=True)
def _enabled():
    _isolated.set_enabled(True)
    yield
    _isolated.set_enabled(True)


def test_runs_in_another_process_and_reuses_it():
    first = _isolated.run_isolated(_pid)
    assert first != os.getpid()
    assert _isolated.run_isolated(_pid) == first


def test_exceptions_from_the_function_propagate():
    with pytest.raises(ValueError, match="bad input"):
        _isolated.run_isolated(_boom)


def test_disabled_runs_in_process():
    _isolated.set_enabled(False)
    assert _isolated.run_isolated(_pid) == os.getpid()


def test_falls_back_in_process_when_no_helper_can_start(monkeypatch):
    def no_pool():
        raise OSError("spawn blocked")

    monkeypatch.setattr(_isolated, "_get_pool", no_pool)
    assert _isolated.run_isolated(_pid) == os.getpid()


def test_compile_failure_in_helper_keeps_the_csv(tmp_path, monkeypatch):
    """finalize_temp_log must report, not raise, when the helper fails, so
    the CSV fallback still runs."""
    from app.serial_logging import decoded_logger as dl

    data = tmp_path / "seg.tmp_data"
    meta = tmp_path / "seg.tmp_meta"
    data.write_text("a,b\n1,2\n", encoding="utf-8")
    meta.write_text("{}", encoding="utf-8")

    def broken(*_a, **_k):
        raise RuntimeError("helper result could not be unpickled")

    monkeypatch.setattr(_isolated, "run_isolated", broken)
    exc = dl.finalize_temp_log(data, meta, tmp_path / "seg.xlsx", {}, keep_csv=True, isolate=True)
    assert isinstance(exc, RuntimeError)
    assert (tmp_path / "seg.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
