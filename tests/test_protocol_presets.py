from __future__ import annotations

import pytest
from app.decoder.protocol_presets import BUILTIN_PRESETS, PRESET_SINGLE_CELL_BMS, PRESET_MODBUS_RTU, PRESET_SIMPLE_HEX_TELEMETRY
from app.decoder.config_loader import load_config


def test_builtin_presets_exist():
    assert "Single Cell BMS (Default)" in BUILTIN_PRESETS
    assert "Simple Hex Telemetry" in BUILTIN_PRESETS
    assert "Modbus RTU Standard" in BUILTIN_PRESETS


def test_builtin_presets_load_cleanly():
    for name, p_dict in BUILTIN_PRESETS.items():
        cfg = load_config(p_dict)
        assert cfg is not None
        assert cfg.protocol is not None
        assert len(cfg.all_signals) > 0
