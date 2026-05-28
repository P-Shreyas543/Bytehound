// =====================================================================
// Bytehound SLIP-framed BMS Simulator
//
// Reference sketch demonstrating Bytehound's escape_mode = "slip" on a
// real device. The INNER frame layout is identical to the main BMS
// sketch (header AA 55 | frame_id LE | length | payload | CRC16 | EE)
// — only the OUTER wire format changes: each inner frame is SLIP-wrapped
// per RFC 1055.
//
//   END = 0xC0 — delimits frames (one at start, one at end).
//   ESC = 0xDB —  inside a frame, ESC + 0xDC means literal 0xC0,
//                  ESC + 0xDD means literal 0xDB.
//
// Match this sketch with app/resources/slip_config_template/ which sets
// escape_mode = slip. The matching smoke test is smoke_slip.py.
//
// To keep the sketch small we only stream BMS_Status (0x1000) and accept
// the Reset Faults TX command at 0x1000 — enough to prove the SLIP
// framing on the wire end-to-end without re-implementing the full BMS.
//
// Build: Arduino IDE 1.8+ / 2.x, board "Arduino Mega 2560" (or any Arduino
// with hardware Serial), 115200 baud.
// =====================================================================

#include <stdint.h>

static const uint8_t SLIP_END     = 0xC0;
static const uint8_t SLIP_ESC     = 0xDB;
static const uint8_t SLIP_ESC_END = 0xDC;
static const uint8_t SLIP_ESC_ESC = 0xDD;

// ---------- CRC16 Modbus ------------------------------------------------
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

// ---------- Telemetry state ---------------------------------------------
static uint16_t pack_voltage_cv = 5000;
static int16_t  pack_current_dA = 20;
static uint8_t  pack_soc_pct    = 75;
static int16_t  pack_temp_dC    = 250;

static unsigned long last_emit_ms  = 0;
static unsigned long last_cycle_ms = 0;

// ---------- SLIP send ---------------------------------------------------
// Emit a single byte with SLIP escaping (does NOT emit the END delimiter).
static void slip_emit_byte(uint8_t b) {
  if (b == SLIP_END) {
    Serial.write(SLIP_ESC);
    Serial.write(SLIP_ESC_END);
  } else if (b == SLIP_ESC) {
    Serial.write(SLIP_ESC);
    Serial.write(SLIP_ESC_ESC);
  } else {
    Serial.write(b);
  }
}

// Build the inner Bytehound frame, then send it SLIP-escaped between two
// END delimiters. The CRC is computed over the UNESCAPED inner bytes; the
// SLIP layer is purely an outer transformation.
static void sendFrame(uint16_t frame_id, const uint8_t *payload, uint8_t payload_length) {
  uint8_t inner[5 + 64 + 2 + 1];
  inner[0] = 0xAA; inner[1] = 0x55;
  inner[2] = (uint8_t)(frame_id & 0xFF);
  inner[3] = (uint8_t)((frame_id >> 8) & 0xFF);
  inner[4] = payload_length;
  for (uint8_t i = 0; i < payload_length; i++) inner[5 + i] = payload[i];
  uint16_t crc = crc16_modbus(inner, 5 + payload_length);
  inner[5 + payload_length]     = (uint8_t)(crc & 0xFF);
  inner[5 + payload_length + 1] = (uint8_t)((crc >> 8) & 0xFF);
  inner[5 + payload_length + 2] = 0xEE;  // footer
  uint16_t total = 5 + payload_length + 3;

  Serial.write(SLIP_END);
  for (uint16_t i = 0; i < total; i++) slip_emit_byte(inner[i]);
  Serial.write(SLIP_END);
}

// ---------- SLIP receive ------------------------------------------------
static uint8_t  slip_buf[128];
static uint8_t  slip_len = 0;
static bool     in_escape = false;

static void on_inner_frame(const uint8_t *frame, uint8_t length);

static void slip_feed(uint8_t b) {
  if (in_escape) {
    if (b == SLIP_ESC_END)      slip_buf[slip_len++] = SLIP_END;
    else if (b == SLIP_ESC_ESC) slip_buf[slip_len++] = SLIP_ESC;
    else                        slip_len = 0;   // bad escape, drop frame
    in_escape = false;
  } else if (b == SLIP_END) {
    if (slip_len > 0) on_inner_frame(slip_buf, slip_len);
    slip_len = 0;
  } else if (b == SLIP_ESC) {
    in_escape = true;
  } else if (slip_len < sizeof(slip_buf)) {
    slip_buf[slip_len++] = b;
  }
}

// ---------- Inner frame handler ----------------------------------------
static void on_inner_frame(const uint8_t *frame, uint8_t length) {
  // Inner = AA 55 | id LE (2) | len (1) | payload | CRC LE (2) | EE
  if (length < 5 + 2 + 1) return;
  if (frame[0] != 0xAA || frame[1] != 0x55) return;
  uint8_t payload_len = frame[4];
  if (length != 5 + payload_len + 2 + 1) return;
  if (frame[length - 1] != 0xEE) return;
  uint16_t want_crc = ((uint16_t)frame[length - 2] << 8) | frame[length - 3];
  uint16_t calc = crc16_modbus(frame, 5 + payload_len);
  if (calc != want_crc) return;
  uint16_t frame_id = ((uint16_t)frame[3] << 8) | frame[2];

  // Reset Faults command (0x1000 with FF FF) — re-seeds telemetry.
  if (frame_id == 0x1000 && payload_len == 2 &&
      frame[5] == 0xFF && frame[6] == 0xFF) {
    pack_voltage_cv = 5000;
    pack_current_dA = 20;
    pack_soc_pct    = 75;
    pack_temp_dC    = 250;
  }
}

// ---------- Telemetry emitter ------------------------------------------
static void emit_1000() {
  uint8_t p[8] = {
    (uint8_t)(pack_voltage_cv & 0xFF), (uint8_t)((pack_voltage_cv >> 8) & 0xFF),
    (uint8_t)(pack_current_dA & 0xFF), (uint8_t)((pack_current_dA >> 8) & 0xFF),
    pack_soc_pct,
    (uint8_t)(pack_temp_dC & 0xFF),    (uint8_t)((pack_temp_dC >> 8) & 0xFF),
    0x00,
  };
  sendFrame(0x1000, p, 8);
}

void setup() {
  Serial.begin(115200);
}

void loop() {
  while (Serial.available() > 0) slip_feed((uint8_t)Serial.read());

  unsigned long now = millis();
  if (now - last_emit_ms >= 100) {
    last_emit_ms = now;
    emit_1000();
  }
  if (now - last_cycle_ms >= 1000) {
    last_cycle_ms = now;
    // Walk values so the host sees motion and so the on-wire bytes
    // occasionally include 0xC0 / 0xDB and force SLIP escaping.
    pack_voltage_cv += 10;
    if (pack_voltage_cv > 6000) pack_voltage_cv = 4000;
    pack_current_dA += 1;
    if (pack_current_dA > 100) pack_current_dA = -50;
    pack_soc_pct = (pack_soc_pct >= 80) ? 70 : (pack_soc_pct + 1);
    pack_temp_dC += 1;
    if (pack_temp_dC > 300) pack_temp_dC = 200;
  }
}
