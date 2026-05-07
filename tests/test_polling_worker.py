from tests.conftest import dummy_protocol_config
import queue
import time
from unittest.mock import MagicMock
from app.serial_io.serial_worker import PollingWorker, SerialSettings
from app.decoder.types import ProtocolConfig, PollingScheduleSpec

def test_polling_worker_queue_interleaving():
    settings = SerialSettings(port="COM99", baud_rate=115200)
    pc = dummy_protocol_config(parser_type="framed")
    sched = PollingScheduleSpec(target_id=0x100, interval_ms=10, timeout_ms=5)
    worker = PollingWorker(settings, pc, [sched])
    
    # Mock the serial port
    worker._serial = MagicMock()
    worker._serial.is_open = True
    worker._serial.in_waiting = 0
    worker._running = True
    
    # Enqueue priority
    worker.enqueue_priority_tx(b"\xAA\xBB")
    
    # We will call worker.run() but we need to stop it after a few iterations
    # We'll override the _running flag inside a side effect or just run the logic manually.
    # Actually it's easier to just call the inside of the loop manually or use a trick.
    
    def mock_write(data):
        if data == b"\xAA\xBB":
            mock_write.priority_sent = True
        else:
            mock_write.poll_sent = True
        # stop after priority is sent
        if getattr(mock_write, 'priority_sent', False):
            worker._running = False
            
    mock_write.priority_sent = False
    mock_write.poll_sent = False
    worker._serial.write = mock_write
    
    worker.start = MagicMock() # don't actually start thread
    worker.run()
    
    assert mock_write.priority_sent
    
