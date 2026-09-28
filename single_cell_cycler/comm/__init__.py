"""Communication layer for Single-Cell BMS Cycler."""

from .protocol_defs import (
    FRAME_CELL_DATA,
    FRAME_BOARD_PARAMS,
    FRAME_FAULT_SOC,
    FRAME_RELAY_CTRL,
    FRAME_CHARGE_SEL,
    FRAME_CHARGE_CTRL,
    FRAME_DISCHARGE_CTRL,
    FRAME_DISCHARGE_SEL,
    HEADER_BYTES,
)
from .packet_codec import (
    CellDataTelemetry,
    BoardParamsTelemetry,
    FaultSoCTelemetry,
    encode_command_packet,
    decode_stream,
)
from .transceiver import SerialTransceiver, TransceiverState

__all__ = [
    "FRAME_CELL_DATA",
    "FRAME_BOARD_PARAMS",
    "FRAME_FAULT_SOC",
    "FRAME_RELAY_CTRL",
    "FRAME_CHARGE_SEL",
    "FRAME_CHARGE_CTRL",
    "FRAME_DISCHARGE_CTRL",
    "FRAME_DISCHARGE_SEL",
    "HEADER_BYTES",
    "CellDataTelemetry",
    "BoardParamsTelemetry",
    "FaultSoCTelemetry",
    "encode_command_packet",
    "decode_stream",
    "SerialTransceiver",
    "TransceiverState",
]
