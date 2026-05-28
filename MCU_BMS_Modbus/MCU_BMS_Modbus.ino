// =====================================================================
// Bytehound Modbus RTU slave  (matches app/resources/modbus_config_template)
//
// Implements the subset of Modbus RTU that Bytehound's host-side parser
// and TX builder use:
//
//   FC 03  Read Holding Registers     — used by polling
//   FC 06  Write Single Register      — used by Parameter Editor / TX
//   FC 16  Write Multiple Registers   — used when the encoded payload > 2 B
//
// The register map exposes the same telemetry as the framed BMS sketch
// so the same end-to-end smoke test (smoke_modbus.py) can verify polling,
// bitfields, enums, TX commands, and parameter writes against a real
// Modbus device:
//
//   Addr   R/W  Type   Description                  Scale on host side
//   ------ ---- ------ ---------------------------- ------------------
//   0x0010 R    uint16 Pack Voltage                 0.01 → V
//   0x0011 R    int16  Pack Current                 0.1  → A
//   0x0012 R    uint16 Pack SOC                     1    → %
//   0x0013 R    int16  Pack Temperature (offset)    0.1, offset −40 → °C
//   0x0020 R    uint16 Cell Voltage 1 (mV)          0.001 → V
//   ...    R    uint16 Cell Voltage 2..8
//   0x0028 RW   uint16 Voltage Limit                0.01 → V
//   0x0030 R    uint16 Status Bits (bitfield, low byte populated)
//   0x0031 R    uint16 BMS State  (enum 0..4, low byte populated)
//
// Bytehound's Modbus polling reads exactly 1 register per request, so each
// logical signal sits at its own register address rather than being packed.
//
// Node address defaults to 1 — matches the bundled modbus_config_template's
// Protocol.modbus_node_address. Change MODBUS_NODE_ADDR below to test the
// node-address override.
//
// Build: Arduino IDE 1.8+ / 2.x, board "Arduino Mega 2560" (or any Arduino
// with hardware Serial), 19200 baud (Modbus convention).
// =====================================================================

#include <stdint.h>

static const uint8_t MODBUS_NODE_ADDR = 1;
static const uint16_t MODBUS_BAUD     = 19200;

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

// ---------- Telemetry state ---------------------------------------------
static uint16_t pack_voltage_cv  = 5000;
static int16_t  pack_current_dA  = 20;
static uint16_t pack_soc_pct     = 75;
static int16_t  pack_temp_dC     = 250;
static uint16_t cell_mV[8]       = { 3700, 3702, 3703, 3699, 3701, 3704, 3700, 3705 };
static uint16_t voltage_limit_cv = 5500;
static uint8_t  status_bits      = 0x81;    // Charging | Ready
static uint8_t  bms_state        = 1;       // Charging (enum 0..4)

static unsigned long last_cycle_ms = 0;

// ---------- Register lookup ---------------------------------------------
// Returns the register value or 0 if address is unknown. The unknown-address
// case lets the master see "0" for un-mapped registers without us emitting an
// exception — Bytehound's polling stays clean and the host-side warnings
// surface the gap.
static uint16_t read_holding(uint16_t addr) {
  switch (addr) {
    case 0x0010: return pack_voltage_cv;
    case 0x0011: return (uint16_t)pack_current_dA;
    case 0x0012: return pack_soc_pct;
    case 0x0013: return (uint16_t)pack_temp_dC;
    case 0x0020: case 0x0021: case 0x0022: case 0x0023:
    case 0x0024: case 0x0025: case 0x0026: case 0x0027:
      return cell_mV[addr - 0x0020];
    case 0x0028: return voltage_limit_cv;
    case 0x0030: return (uint16_t)status_bits;
    case 0x0031: return (uint16_t)bms_state;
    default:     return 0;
  }
}

// Returns true if the write was accepted. The Parameter Editor writes
// Voltage Limit; any other write is silently ignored (the master sees a
// successful FC06 echo, the simulator just doesn't update anything).
static bool write_holding(uint16_t addr, uint16_t value) {
  if (addr == 0x0028) {
    if (value >= 4000 && value <= 6000) {
      voltage_limit_cv = value;
      return true;
    }
  }
  return false;
}

// ---------- Modbus RTU frame send (response) ----------------------------
static void send_response(const uint8_t *frame, uint8_t length) {
  uint16_t crc = crc16_modbus(frame, length);
  Serial.write(frame, length);
  Serial.write((uint8_t)(crc & 0xFF));
  Serial.write((uint8_t)((crc >> 8) & 0xFF));
}

// FC03 response: [addr][03][byte_count][hi][lo]...[crc lo][crc hi]
static void handle_read_holding(uint16_t start_addr, uint16_t count) {
  if (count == 0 || count > 125) return;       // spec: 1..125 regs
  uint8_t resp[3 + 2 * 125];
  resp[0] = MODBUS_NODE_ADDR;
  resp[1] = 0x03;
  resp[2] = (uint8_t)(count * 2);
  for (uint16_t i = 0; i < count; i++) {
    uint16_t v = read_holding(start_addr + i);
    resp[3 + i * 2]     = (uint8_t)((v >> 8) & 0xFF);  // big-endian per spec
    resp[3 + i * 2 + 1] = (uint8_t)(v & 0xFF);
  }
  send_response(resp, 3 + count * 2);
}

// FC06 echo: [addr][06][reg hi][reg lo][val hi][val lo][crc lo][crc hi]
static void handle_write_single(uint16_t addr, uint16_t value) {
  write_holding(addr, value);
  uint8_t resp[6] = {
    MODBUS_NODE_ADDR, 0x06,
    (uint8_t)((addr >> 8) & 0xFF),  (uint8_t)(addr & 0xFF),
    (uint8_t)((value >> 8) & 0xFF), (uint8_t)(value & 0xFF),
  };
  send_response(resp, 6);
}

// FC16 echo: [addr][16][start hi][start lo][qty hi][qty lo][crc lo][crc hi]
static void handle_write_multiple(uint16_t addr, uint16_t qty, const uint8_t *values) {
  for (uint16_t i = 0; i < qty; i++) {
    uint16_t v = ((uint16_t)values[i * 2] << 8) | values[i * 2 + 1];
    write_holding(addr + i, v);
  }
  uint8_t resp[6] = {
    MODBUS_NODE_ADDR, 0x10,
    (uint8_t)((addr >> 8) & 0xFF), (uint8_t)(addr & 0xFF),
    (uint8_t)((qty >> 8) & 0xFF),  (uint8_t)(qty & 0xFF),
  };
  send_response(resp, 6);
}

// ---------- Modbus RTU frame receive ------------------------------------
// 3.5-char inter-frame timeout (about 2 ms at 19200) is approximated by a
// simple "no byte for N ms" gate so we can declare the request complete
// without parsing the function-code's length up front.
static uint8_t  rx_buf[256];
static uint8_t  rx_len = 0;
static unsigned long rx_last_byte_ms = 0;
static const unsigned long INTER_FRAME_GAP_MS = 5;

static void process_request(const uint8_t *frame, uint8_t length) {
  if (length < 4) return;
  if (frame[0] != MODBUS_NODE_ADDR) return;    // not addressed to us
  uint16_t want_crc = ((uint16_t)frame[length - 1] << 8) | frame[length - 2];
  uint16_t calc_crc = crc16_modbus(frame, length - 2);
  if (want_crc != calc_crc) return;
  uint8_t fc = frame[1];
  if (fc == 0x03 && length == 8) {
    uint16_t addr  = ((uint16_t)frame[2] << 8) | frame[3];
    uint16_t count = ((uint16_t)frame[4] << 8) | frame[5];
    handle_read_holding(addr, count);
  } else if (fc == 0x06 && length == 8) {
    uint16_t addr  = ((uint16_t)frame[2] << 8) | frame[3];
    uint16_t value = ((uint16_t)frame[4] << 8) | frame[5];
    handle_write_single(addr, value);
  } else if (fc == 0x10 && length >= 9) {
    uint16_t addr = ((uint16_t)frame[2] << 8) | frame[3];
    uint16_t qty  = ((uint16_t)frame[4] << 8) | frame[5];
    uint8_t  byte_count = frame[6];
    if (byte_count + 9 == length) {
      handle_write_multiple(addr, qty, &frame[7]);
    }
  }
}

// ---------- Setup / loop ------------------------------------------------
void setup() {
  Serial.begin(MODBUS_BAUD);
}

void loop() {
  unsigned long now = millis();

  // Read bytes; collect into rx_buf, declare a frame complete after a
  // gap of >= INTER_FRAME_GAP_MS.
  while (Serial.available() > 0 && rx_len < sizeof(rx_buf)) {
    rx_buf[rx_len++] = (uint8_t)Serial.read();
    rx_last_byte_ms = now;
  }
  if (rx_len > 0 && (now - rx_last_byte_ms) >= INTER_FRAME_GAP_MS) {
    process_request(rx_buf, rx_len);
    rx_len = 0;
  }

  // Walk telemetry slowly so the host sees motion in pack values, cells,
  // SOC, and the packed status word.
  if (now - last_cycle_ms >= 1000) {
    last_cycle_ms = now;
    pack_voltage_cv += 10;
    if (pack_voltage_cv > 6000) pack_voltage_cv = 4000;
    pack_current_dA += 1;
    if (pack_current_dA > 100) pack_current_dA = -50;
    pack_soc_pct = (pack_soc_pct >= 80) ? 70 : (pack_soc_pct + 1);
    pack_temp_dC += 1;
    if (pack_temp_dC > 300) pack_temp_dC = 200;
    for (uint8_t i = 0; i < 8; i++) {
      int16_t delta = ((int16_t)((millis() ^ (i * 17)) & 0x7)) - 3;
      int32_t next = (int32_t)cell_mV[i] + delta;
      if (next < 3650) next = 3650;
      if (next > 3750) next = 3750;
      cell_mV[i] = (uint16_t)next;
    }
    // Rotate the bitfield's low 4 bits, keep Ready bit latched, advance
    // the state through 0..4.
    uint8_t low = (status_bits & 0x0F) << 1;
    if (low == 0 || low > 0x0F) low = 0x01;
    status_bits = (status_bits & 0xF0) | low;
    bms_state = (bms_state + 1) % 5;
  }
}
