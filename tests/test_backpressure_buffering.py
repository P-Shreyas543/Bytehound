"""Unit tests for cursor-compacted stream buffering and backpressure throttling."""

from collections import deque
from unittest.mock import MagicMock

import pytest

from app.protocol.packet_builder import build_packet
from app.protocol.packet_parser import FramedParser, WaveshareCanParser
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.ui.telemetry_pipeline import TelemetryPipelineMixin
from tests.conftest import dummy_protocol_config


class TestCursorCompactedBuffering:
    """Tests the sliding cursor and amortized compaction in FramedParser and WaveshareCanParser."""

    def test_framed_parser_streaming_and_compaction(self):
        pc = dummy_protocol_config(
            header=b"\xAA\x55",
            footer=b"\x0D\x0A",
            frame_id_size=2,
            frame_id_byte_order="little",
            length_size=2,
            length_byte_order="little",
            length_meaning="payload_only",
            crc_type="crc16_ccitt",
            crc_size=2,
            crc_byte_order="little",
            crc_coverage="header_to_payload",
        )
        parser = FramedParser(pc)

        # Generate 200 packets to exceed the 8192 compaction threshold
        packets = []
        raw_stream = bytearray()
        for i in range(200):
            payload = f"packet_data_{i:04d}".encode("ascii")
            pkt_bytes = build_packet(pc, frame_id=0x1000 + (i % 16), payload=payload)
            packets.append((0x1000 + (i % 16), payload, pkt_bytes))
            raw_stream.extend(pkt_bytes)

        # Feed in chunks of irregular sizes (fragmented stream)
        chunk_size = 37
        extracted_all = []
        for offset in range(0, len(raw_stream), chunk_size):
            chunk = bytes(raw_stream[offset : offset + chunk_size])
            parser.feed(chunk)
            pkts = parser.extract_all()
            extracted_all.extend(pkts)

        assert len(extracted_all) == 200
        for i, (fid, payload, pkt_bytes) in enumerate(packets):
            parsed = extracted_all[i]
            assert parsed.ok is True
            assert parsed.frame_id == fid
            assert parsed.payload == payload
            assert parsed.raw == pkt_bytes

        assert parser.buffered_bytes == 0
        assert parser._offset == 0
        assert len(parser._buf) == 0

    def test_buffered_bytes_accuracy_with_partial_frame(self):
        pc = dummy_protocol_config(
            header=b"\xAA\x55",
            footer=b"\x0D\x0A",
            frame_id_size=2,
            frame_id_byte_order="little",
            length_size=2,
            length_byte_order="little",
            length_meaning="payload_only",
            crc_type="crc16_ccitt",
            crc_size=2,
            crc_byte_order="little",
            crc_coverage="header_to_payload",
        )
        parser = FramedParser(pc)

        pkt_bytes = build_packet(pc, frame_id=0x1234, payload=b"hello_world")
        # Feed complete packet + first 5 bytes of next packet
        parser.feed(pkt_bytes + pkt_bytes[:5])
        assert parser.buffered_bytes == len(pkt_bytes) + 5

        extracted = parser.extract_all()
        assert len(extracted) == 1
        assert extracted[0].frame_id == 0x1234
        # Remaining buffer should be exactly 5 bytes
        assert parser.buffered_bytes == 5
        assert parser._offset == len(pkt_bytes)

        # Feed remaining part of second packet
        parser.feed(pkt_bytes[5:])
        assert parser.buffered_bytes == len(pkt_bytes)

        extracted2 = parser.extract_all()
        assert len(extracted2) == 1
        assert extracted2[0].frame_id == 0x1234
        assert parser.buffered_bytes == 0

    def test_waveshare_can_parser_compaction(self):
        pc = dummy_protocol_config(
            header=b"\xAA",
            footer=b"\x55",
            parser_type="waveshare_can_20_bytes",
            waveshare_fixed_20_bytes=True,
        )
        parser = WaveshareCanParser(pc)

        # Build valid 20-byte Waveshare frames
        # Frame: AA 55 [type 1B] [rev 1B] [rev 1B] [id 4B little] [dlc 1B] [data 8B] [chk 1B]
        frames = []
        raw_stream = bytearray()
        for i in range(100):
            frame = bytearray(20)
            frame[0] = 0xAA
            frame[1] = 0x55
            frame[5] = i & 0xFF
            frame[6] = (i >> 8) & 0xFF
            frame[9] = 4  # DLC = 4
            frame[10:14] = b"TEST"
            chk = (sum(frame[:19]) + 1) & 0xFF
            frame[19] = chk
            frames.append(bytes(frame))
            raw_stream.extend(frame)

        # Feed in chunks
        chunk_size = 53
        extracted = []
        for offset in range(0, len(raw_stream), chunk_size):
            parser.feed(bytes(raw_stream[offset : offset + chunk_size]))
            extracted.extend(parser.extract_all())

        assert len(extracted) == 100
        for i in range(100):
            assert extracted[i].ok is True
            assert extracted[i].frame_id == i
            assert extracted[i].payload == b"TEST"
        assert parser.buffered_bytes == 0


class TestBackpressureControl:
    """Tests backpressure signaling in PollingWorker and TelemetryPipelineMixin."""

    def test_worker_set_backpressure(self):
        settings = SerialSettings(port="COM99", baud_rate=115200)
        protocol = dummy_protocol_config()
        worker = PollingWorker(settings, protocol, [])

        assert worker.is_backpressured is False
        assert worker.backpressure_events == 0

        events = []
        worker.backpressure_changed.connect(events.append)

        # Engage backpressure
        worker.set_backpressure(True)
        assert worker.is_backpressured is True
        assert worker.backpressure_events == 1
        assert events == [True]

        # Duplicate engagement should not fire event or increment count
        worker.set_backpressure(True)
        assert worker.backpressure_events == 1
        assert len(events) == 1

        # Release backpressure
        worker.set_backpressure(False)
        assert worker.is_backpressured is False
        assert worker.backpressure_events == 1
        assert events == [True, False]

    def test_telemetry_pipeline_watermark_backpressure(self):
        class DummyWindow(TelemetryPipelineMixin):
            def __init__(self):
                self._pending_packets = deque(maxlen=10_000)
                self._serial = MagicMock()
                self._session_started = None
                self._plot_last_redraw = 0.0
                self._plot_redraw_interval_s = 0.05
                self._console = MagicMock()

            def _handle_packet(self, packet, pre_decoded=None):
                pass

            def _refresh_counts_label(self):
                pass

            def _redraw_plot(self):
                pass

            @property
            def _table_model(self):
                m = MagicMock()
                return m

        win = DummyWindow()

        # Small batch under watermark
        small_batch = [("pkt", None)] * 500
        win._on_packets_received(small_batch)
        win._serial.set_backpressure.assert_not_called()
        assert getattr(win, "_ui_backpressured", False) is False

        # Large batch pushing total past BACKPRESSURE_HIGH_WATERMARK (4000)
        large_batch = [("pkt", None)] * 3600
        win._on_packets_received(large_batch)
        win._serial.set_backpressure.assert_called_once_with(True)
        assert win._ui_backpressured is True

        # Flush UI clears the queue and releases backpressure
        win._serial.reset_mock()
        win._flush_ui_inner()
        win._serial.set_backpressure.assert_called_once_with(False)
        assert win._ui_backpressured is False
        assert len(win._pending_packets) == 0
