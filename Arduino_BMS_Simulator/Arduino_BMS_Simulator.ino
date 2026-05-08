// =====================================================================
// Serial-MonitorApp Compatible BMS Simulator
//
// Protocol: AA 55 | Frame ID (2 LE) | Length (1) | Payload | CRC16 (2 LE) | EE
// CRC16 Modbus over header..payload (poly 0x8005 reflected, init 0xFFFF)
//
// Streams three telemetry frames and reacts to two TX commands:
//   RX (board -> PC):
//     0x1000 BMS_Status     uint16 Voltage (LE, scale 0.1)
//                           int16  Current (LE, scale 0.1)         every 100 ms
//     0x2000 BMS_Settings   uint16 Voltage_Limit (LE, scale 0.1)   every 500 ms
//     0x3000 Status_Flags   uint8  Status_Bits (bitfield)
//                           uint8  Mode (enum 0..4)                every 200 ms
//
//   TX (PC -> board):
//     0x1001 Reset             payload "FF FF" - zero counters/flags
//     0x2000 (write)           payload uint16 LE (scale 0.1) - direct register
//                                                              write to Voltage_Limit
//                                                              (used by GUI parameter editor)
//     0x2001 Set_Voltage_Limit payload uint16 LE (scale 0.1) - same effect via the
//                                                              named TX command
//
// Build: Arduino IDE 1.8+ / 2.x, board "Arduino Mega 2560" (or any Arduino
// with hardware Serial), 115200 baud.
// =====================================================================

#include <stdint.h>

// ---------- CRC16 Modbus (poly 0x8005 reflected, init 0xFFFF) -----------
static uint16_t crc16_modbus(const uint8_t *data, uint16_t length) {
  uint16_t crc = 0xFFFF;
  for (uint16_t i = 0; i < length; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      crc = (crc & 1) ? ((crc >> 1) ^ 0xA001) : (crc >> 1);
    }
  }
  return crc;
}

// ---------- Send one framed packet --------------------------------------
static void sendFrame(uint16_t frame_id, const uint8_t *payload, uint8_t payload_length) {
  uint8_t header[5];
  header[0] = 0xAA;
  header[1] = 0x55;
  header[2] = (uint8_t)(frame_id & 0xFF);          // LE low
  header[3] = (uint8_t)((frame_id >> 8) & 0xFF);   // LE high
  header[4] = payload_length;
  Serial.write(header, 5);
  if (payload_length && payload) Serial.write(payload, payload_length);

  uint16_t crc = crc16_modbus(header, 5);
  if (payload_length && payload) {
    for (uint16_t i = 0; i < payload_length; i++) {
      crc ^= payload[i];
      for (int j = 0; j < 8; j++) {
        crc = (crc & 1) ? ((crc >> 1) ^ 0xA001) : (crc >> 1);
      }
    }
  }
  uint8_t tail[3] = { (uint8_t)(crc & 0xFF), (uint8_t)((crc >> 8) & 0xFF), 0xEE };
  Serial.write(tail, 3);
}

// ---------- Telemetry state ---------------------------------------------
static uint16_t voltage_dV    = 500;   // 50.0 V
static int16_t  current_dA    = 20;    // 2.0 A
static uint16_t voltage_limit = 550;   // 55.0 V (writable via Set_Voltage_Limit)

// Bitfield: 0=Charging 1=Discharging 2=Balancing 3=Fault
//           4=OverVoltage 5=UnderVoltage 6=OverTemp 7=Ready
static uint8_t  status_bits   = 0x81;  // Charging | Ready
static uint8_t  mode          = 1;     // Charging (enum 0..4)

static unsigned long last_1000_ms = 0;
static unsigned long last_2000_ms = 0;
static unsigned long last_3000_ms = 0;
static unsigned long last_cycle_ms = 0;

// ---------- RX state machine --------------------------------------------
// Accepts AA 55 | id LE (2) | len (1) | payload | crc LE (2) | EE.
// Validates CRC; on success calls on_command() with the parsed frame.
enum RxState : uint8_t {
  RX_HDR1, RX_HDR2, RX_ID_LO, RX_ID_HI, RX_LEN,
  RX_PAYLOAD, RX_CRC_LO, RX_CRC_HI, RX_FOOTER
};
static RxState rx_state = RX_HDR1;
static uint16_t rx_frame_id = 0;
static uint8_t  rx_len = 0;
static uint8_t  rx_payload[32];
static uint8_t  rx_idx = 0;
static uint16_t rx_crc_recv = 0;

static void on_command(uint16_t frame_id, const uint8_t *payload, uint8_t length);

static void rx_feed(uint8_t b) {
  switch (rx_state) {
    case RX_HDR1:    rx_state = (b == 0xAA) ? RX_HDR2 : RX_HDR1; break;
    case RX_HDR2:    rx_state = (b == 0x55) ? RX_ID_LO : RX_HDR1; break;
    case RX_ID_LO:   rx_frame_id = b;             rx_state = RX_ID_HI; break;
    case RX_ID_HI:   rx_frame_id |= ((uint16_t)b << 8); rx_state = RX_LEN; break;
    case RX_LEN:
      rx_len = b;
      rx_idx = 0;
      if (rx_len > sizeof(rx_payload)) { rx_state = RX_HDR1; break; }
      rx_state = (rx_len == 0) ? RX_CRC_LO : RX_PAYLOAD;
      break;
    case RX_PAYLOAD:
      rx_payload[rx_idx++] = b;
      if (rx_idx >= rx_len) rx_state = RX_CRC_LO;
      break;
    case RX_CRC_LO:  rx_crc_recv = b; rx_state = RX_CRC_HI; break;
    case RX_CRC_HI:  rx_crc_recv |= ((uint16_t)b << 8); rx_state = RX_FOOTER; break;
    case RX_FOOTER:
      if (b == 0xEE) {
        uint8_t buf[5 + 32];
        buf[0] = 0xAA; buf[1] = 0x55;
        buf[2] = (uint8_t)(rx_frame_id & 0xFF);
        buf[3] = (uint8_t)((rx_frame_id >> 8) & 0xFF);
        buf[4] = rx_len;
        for (uint8_t i = 0; i < rx_len; i++) buf[5 + i] = rx_payload[i];
        uint16_t crc_calc = crc16_modbus(buf, 5 + rx_len);
        if (crc_calc == rx_crc_recv) {
          on_command(rx_frame_id, rx_payload, rx_len);
        }
      }
      rx_state = RX_HDR1;
      break;
  }
}

// ---------- Command dispatch --------------------------------------------
// Empty-payload frames (length 0) are interpreted as poll requests and
// trigger an immediate fresh emission of the matching telemetry frame.
// Non-empty payloads are interpreted as commands per tx_commands.csv.
static void emit_1000(); static void emit_2000(); static void emit_3000();

static void on_command(uint16_t frame_id, const uint8_t *payload, uint8_t length) {
  // Poll requests: empty payload, just echo current telemetry for that ID.
  if (length == 0) {
    if (frame_id == 0x1000) { emit_1000(); return; }
    if (frame_id == 0x2000) { emit_2000(); return; }
    if (frame_id == 0x3000) { emit_3000(); return; }
    return;
  }

  // Reset: 0x1001 with FF FF.
  if (frame_id == 0x1001 && length == 2 && payload[0] == 0xFF && payload[1] == 0xFF) {
    voltage_dV = 500;
    current_dA = 20;
    status_bits = 0x80; // Ready only
    mode = 0;           // Idle
    return;
  }

  // Voltage_Limit write — accepted at BOTH the variable's address (0x2000,
  // used by the GUI parameter editor when committing a new value to a R/W
  // signal) AND the named TX command's address (0x2001, used by anything
  // calling tx_commands.csv -> Set_Voltage_Limit). uint16 LE in deci-volts.
  if ((frame_id == 0x2000 || frame_id == 0x2001) && length == 2) {
    uint16_t requested = (uint16_t)payload[0] | ((uint16_t)payload[1] << 8);
    if (requested >= 400 && requested <= 600) {  // 40.0 - 60.0 V
      voltage_limit = requested;
      // Push the new value out immediately so the test (and a human watching
      // the UI) can confirm the round-trip without waiting for the next tick.
      emit_2000();
    }
    return;
  }
}

// ---------- Periodic emitters -------------------------------------------
static void emit_1000() {
  uint8_t p[4] = {
    (uint8_t)(voltage_dV & 0xFF), (uint8_t)((voltage_dV >> 8) & 0xFF),
    (uint8_t)(current_dA & 0xFF), (uint8_t)((current_dA >> 8) & 0xFF),
  };
  sendFrame(0x1000, p, 4);
}

static void emit_2000() {
  uint8_t p[2] = {
    (uint8_t)(voltage_limit & 0xFF), (uint8_t)((voltage_limit >> 8) & 0xFF),
  };
  sendFrame(0x2000, p, 2);
}

static void emit_3000() {
  uint8_t p[2] = { status_bits, mode };
  sendFrame(0x3000, p, 2);
}

// ---------- Setup / loop ------------------------------------------------
void setup() {
  Serial.begin(115200);
}

void loop() {
  // Drain any incoming bytes through the RX state machine.
  while (Serial.available() > 0) {
    rx_feed((uint8_t)Serial.read());
  }

  unsigned long now = millis();

  if (now - last_1000_ms >= 100) {
    last_1000_ms = now;
    emit_1000();
  }
  if (now - last_2000_ms >= 500) {
    last_2000_ms = now;
    emit_2000();
  }
  if (now - last_3000_ms >= 200) {
    last_3000_ms = now;
    emit_3000();
  }

  // Slowly walk telemetry + cycle the bitfield/enum so the UI shows motion.
  if (now - last_cycle_ms >= 1000) {
    last_cycle_ms = now;

    voltage_dV += 1;
    if (voltage_dV > 600) voltage_dV = 400;     // 40.0 - 60.0 V

    current_dA += 1;
    if (current_dA > 100) current_dA = -50;     // -5.0 - 10.0 A

    // Cycle bits: shift the lower 4 status bits, keep "Ready" (bit 7) latched.
    uint8_t low = (status_bits & 0x0F) << 1;
    if (low == 0 || low > 0x0F) low = 0x01;
    status_bits = (status_bits & 0xF0) | low;

    mode = (mode + 1) % 5;                      // 0..4 cycles through Idle..Service
  }
}
