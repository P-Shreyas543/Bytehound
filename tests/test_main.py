"""Tests for app.main."""

from __future__ import annotations

from app.main import main

def test_config_validator_cli_valid(tmp_path, monkeypatch, capsys):
    source = tmp_path / "config.json"
    import json
    data = {
        "protocol": [
            {
                "profile_name": "Valid CLI Test",
                "header_hex": "AA55",
                "frame_id_size": 2,
                "frame_id_byte_order": "big",
                "length_size": 1,
                "length_meaning": "payload_only",
                "crc_type": "crc16_modbus",
                "crc_size": 2,
                "crc_byte_order": "little",
                "enabled": "TRUE"
            }
        ],
        "variables": [
            {
                "id_or_address": "0x0010",
                "signal_name": "Voltage",
                "data_type": "uint16",
                "count": 1,
                "byte_order": "big",
                "scale": 1,
                "offset": 0,
                "unit": "V",
                "enabled": "TRUE"
            }
        ]
    }
    source.write_text(json.dumps(data), encoding="utf-8")

    # Run main with --validate flag
    rc = main(["--validate", str(source)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "OK: Config" in captured.out
    assert "valid" in captured.out

def test_config_validator_cli_invalid(tmp_path, monkeypatch, capsys):
    # Pass a non-existent file
    rc = main(["--validate", str(tmp_path / "does_not_exist.json")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "ERROR: Config validation failed" in captured.err
