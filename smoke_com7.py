import serial
import time
from app.decoder.config_loader import load_config
from app.protocol.packet_parser import create_parser
from app.decoder.frame_decoder import decode_frame

c = load_config('app/resources/config_template')
p = create_parser(c.protocol)
s = serial.Serial('COM7', 115200, timeout=1)
t0 = time.time()

print("Listening on COM7...")
while time.time() - t0 < 3:
    d = s.read(100)
    p.feed(d)
    for pkt in p.extract_all():
        if not pkt.ok:
            print('ERR', pkt.error)
        else:
            print(decode_frame(c, pkt.frame_id, pkt.payload))
