// =====================================================================
// Bytehound Compatible BMS Simulator  (matches app/resources/config_template)
//
// Protocol: AA 55 | Frame ID (2 LE) | Length (1) | Payload | CRC16 (2 LE) | EE
// CRC16 Modbus over header..payload (poly 0x8005 reflected, init 0xFFFF)
//
// Compatible with Bytehound v0.3.1 features:
//   - Auto-Reconnect: Simulates disconnect behaviors via 0x1004 go_silent.
//   - Memory Cap & Warnings: Telemetry packet streams are compatible with host-side
//     memory caps and queue saturation indicators.
//
// Streams three telemetry frames and reacts to several TX commands.
//
//   RX (board -> PC):
//     0x1000 BMS_Status     uint16 Pack Voltage  (LE, scale 0.01)
//                           int16  Pack Current  (LE, scale 0.1)
//                           uint8  Pack SOC      (scale 1)
//                           int16  Pack Temp     (LE, scale 0.1, offset -40)
//                                                              every 100 ms (8 bytes)
//     0x2000 BMS_Settings   uint16[8] Cell Voltage (LE, scale 0.001)
//                           uint16   Voltage Limit (LE, scale 0.01) RW
//                                                              every 500 ms (18 bytes)
//     0x3000 Status_Flags   uint8  Fault Flags (bitfield)
//                           uint8  BMS State   (enum 0..4)
//                                                              every 200 ms (2 bytes)
//
//   TX (PC -> board):
//     0x1000 Reset Faults      payload "FF FF" — zero counters/flags
//     0x2000 (write)           payload 2 bytes  uint16 LE (Voltage Limit only,
//                                                          scale 0.01) — short
//                                                          form used by the
//                                                          GUI parameter editor.
//                              payload 18 bytes — full-frame echo write; only
//                                                 the last 2 bytes (Voltage
//                                                 Limit slot) are honoured.
//     0x2001 Set_Voltage_Limit payload uint16 LE (scale 0.01) — same effect via
//                                                               the named TX
//                                                               command.
//
//   Test hooks (used by smoke_headless.py and smoke_stress.py):
//     0x1002 stress_mode       payload uint8 (1=on, 0=off) - 5x faster
//                                                            telemetry cadence
//     0x1003 inject_crc_errors payload uint8 N            - emit next N
//                                                            telemetry frames
//                                                            with deliberately
//                                                            corrupted CRC
//     0x1004 go_silent         payload uint8 seconds      - suppress all RX
//                                                            for N seconds
//                                                            (tests watchdog)
//     0x1005 streaming_mode    payload uint8 (1=off, 0=on, default on) -
//                                                            disables the
//                                                            autonomous
//                                                            telemetry timers
//                                                            so smoke_headless
//                                                            can measure the
//                                                            polling-only
//                                                            arrival cadence.
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

// ---------- Test-hook state ---------------------------------------------
// pending_crc_corruptions: when > 0, the next sendFrame() XORs the high CRC
//   byte with 0xFF before transmitting, then decrements. This is how the
//   stress test exercises the host-side CRC error counter.
// silent_until_ms: while millis() < silent_until_ms, all telemetry emission
//   is suppressed. The host uses this to verify the data-watchdog fires.
// stress_mode_on: 5x faster cadence on the periodic emitters.
// streaming_on: when false, the autonomous timer-driven emitters in loop()
//   are suppressed. Poll-driven responses in on_command() still work, so
//   smoke_headless.py uses this to measure polling cadence deterministically
//   (without the firmware also racing the host at the timer interval).
static uint8_t        pending_crc_corruptions = 0;
static unsigned long  silent_until_ms = 0;
static bool           stress_mode_on = false;
static bool           streaming_on   = true;

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
  // Stress-test hook: corrupt the CRC bytes of the next N frames so the host
  // sees real on-the-wire CRC failures. The footer is left intact so the
  // parser still aligns; only the CRC mismatches.
  if (pending_crc_corruptions > 0) {
    crc ^= 0xFF00;  // flip the high byte
    pending_crc_corruptions--;
  }
  uint8_t tail[3] = { (uint8_t)(crc & 0xFF), (uint8_t)((crc >> 8) & 0xFF), 0xEE };
  Serial.write(tail, 3);
}

// ---------- Telemetry state ---------------------------------------------
// 0x1000 BMS_Status (uint16 + int16 + uint8 + int16 = 7 bytes; padded to 8
// on the wire to match the variables.csv layout). Scales come from the
// bundled variables.csv so a host using the default config decodes to the
// same engineering values shown in the comments.
static uint16_t pack_voltage_cv = 5000;   // 50.00 V  (scale 0.01 → 5000)
static int16_t  pack_current_dA = 20;     // 2.0 A    (scale 0.1)
static uint8_t  pack_soc_pct    = 75;     // 75 %
static int16_t  pack_temp_dC    = 250;    // 25.0 °C  (scale 0.1, offset -40)

// 0x2000 BMS_Settings (8x cell voltages + voltage limit = 18 bytes).
// Cell voltages drift slightly so CalcGroups (min/max/avg/diff) has real
// spread to compute over. The 8 cells are ordered low → high index.
static uint16_t cell_mV[8] = { 3700, 3702, 3703, 3699, 3701, 3704, 3700, 3705 };
static uint16_t voltage_limit_cv = 5500;  // 55.00 V (writable, scale 0.01)

// 0x3000 Status_Flags
// Bitfield: 0=Charging 1=Discharging 2=Balancing 3=Fault
//           4=Overvoltage 5=Undervoltage 6=Overtemp 7=Ready
static uint8_t  status_bits = 0x81;       // Charging | Ready
static uint8_t  mode        = 1;          // Charging (enum 0..4)

static unsigned long last_1000_ms = 0;
static unsigned long last_2000_ms = 0;
static unsigned long last_3000_ms = 0;
static unsigned long last_cycle_ms = 0;

// ---------- RX state machine --------------------------------------------
// Accepts AA 55 | id LE (2) | len (1) | payload | crc LE (2) | EE.
// Validates CRC; on success calls on_command() with the parsed frame.
// Buffer sized to 64 to safely hold full 18-byte 0x2000 writes from the
// host's Parameter Editor and any future-larger commands.
enum RxState : uint8_t {
  RX_HDR1, RX_HDR2, RX_ID_LO, RX_ID_HI, RX_LEN,
  RX_PAYLOAD, RX_CRC_LO, RX_CRC_HI, RX_FOOTER
};
static RxState rx_state = RX_HDR1;
static uint16_t rx_frame_id = 0;
static uint8_t  rx_len = 0;
static uint8_t  rx_payload[64];
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
        uint8_t buf[5 + 64];
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
  // Suppressed during silent-mode so we can verify the host watchdog.
  if (length == 0) {
    if (millis() < silent_until_ms) return;
    if (frame_id == 0x1000) { emit_1000(); return; }
    if (frame_id == 0x2000) { emit_2000(); return; }
    if (frame_id == 0x3000) { emit_3000(); return; }
    return;
  }

  // Reset Faults: 0x1000 with FF FF (matches tx_commands.csv "Reset Faults").
  // Also accept 0x1001 for backward compatibility with older configs that
  // used a dedicated reset frame ID.
  if ((frame_id == 0x1000 || frame_id == 0x1001) &&
      length == 2 && payload[0] == 0xFF && payload[1] == 0xFF) {
    pack_voltage_cv = 5000;
    pack_current_dA = 20;
    pack_soc_pct = 75;
    pack_temp_dC = 250;
    status_bits = 0x80; // Ready only
    mode = 0;           // Idle
    pending_crc_corruptions = 0;
    silent_until_ms = 0;
    stress_mode_on = false;
    streaming_on = true;  // re-enable autonomous emission so a Reset undoes any 0x1005 toggle
    return;
  }

  // Voltage Limit write — accepted at BOTH the variable's frame (0x2000,
  // used by the GUI parameter editor when committing a new value to an RW
  // signal) AND the named TX command's frame (0x2001, used by anything
  // calling tx_commands.csv -> Set_Voltage_Limit). uint16 LE, scale 0.01
  // (centi-volts), so 5500 = 55.00 V. Range is enforced 40.00–60.00 V.
  //
  // Two payload sizes accepted:
  //   * 2 bytes  → just the Voltage Limit (parameter-editor short form).
  //   * 18 bytes → full 0x2000 frame echo; only the last 2 bytes (the
  //                Voltage Limit slot at byte 16) are honoured.
  if (frame_id == 0x2000 || frame_id == 0x2001) {
    uint16_t requested = 0;
    bool have_request = false;
    if (length == 2) {
      requested = (uint16_t)payload[0] | ((uint16_t)payload[1] << 8);
      have_request = true;
    } else if (length == 18) {
      requested = (uint16_t)payload[16] | ((uint16_t)payload[17] << 8);
      have_request = true;
    }
    if (have_request && requested >= 4000 && requested <= 6000) {  // 40.00–60.00 V
      voltage_limit_cv = requested;
      // Push the new value out immediately so the test (and a human watching
      // the UI) can confirm the round-trip without waiting for the next tick.
      emit_2000();
    }
    return;
  }

  // ----- Stress-test hooks --------------------------------------------
  // 0x1002 [01|00] : enable / disable 5x cadence stress mode.
  if (frame_id == 0x1002 && length == 1) {
    stress_mode_on = (payload[0] != 0);
    return;
  }
  // 0x1003 [N] : the next N telemetry frames will have corrupted CRC.
  if (frame_id == 0x1003 && length == 1) {
    pending_crc_corruptions = payload[0];
    return;
  }
  // 0x1004 [seconds] : suppress all telemetry for `seconds` seconds so the
  //                    host can prove its data-watchdog fires.
  if (frame_id == 0x1004 && length == 1) {
    silent_until_ms = millis() + (unsigned long)payload[0] * 1000UL;
    return;
  }
  // 0x1005 [0|1] : disable / enable autonomous timer-driven emission.
  //                Default is enabled (so a freshly plugged-in board streams
  //                without prompting). smoke_headless sends [01] so the
  //                polling cadence phase can measure polling-only behaviour
  //                without the firmware racing the host at the timer rate.
  if (frame_id == 0x1005 && length == 1) {
    streaming_on = (payload[0] == 0);
    return;
  }
}

// ---------- Periodic emitters -------------------------------------------
// emit_1000 sends 8 bytes: u16 voltage | i16 current | u8 soc | i16 temp | pad.
// Variables.csv computes signal offsets sequentially from the data_type widths
// (2+2+1+2 = 7 bytes), and the bundled frames.csv declares payload_length=8,
// so we pad to 8 bytes with a trailing zero. The decoder ignores trailing
// bytes past the last declared signal.
static void emit_1000() {
  uint8_t p[8] = {
    (uint8_t)(pack_voltage_cv & 0xFF), (uint8_t)((pack_voltage_cv >> 8) & 0xFF),
    (uint8_t)(pack_current_dA & 0xFF), (uint8_t)((pack_current_dA >> 8) & 0xFF),
    pack_soc_pct,
    (uint8_t)(pack_temp_dC & 0xFF),    (uint8_t)((pack_temp_dC >> 8) & 0xFF),
    0x00,  // padding to reach payload_length=8
  };
  sendFrame(0x1000, p, 8);
}

// emit_2000 sends 18 bytes: 8 × u16 cell voltage (LE) followed by u16
// voltage_limit (LE). This matches the bundled variables.csv layout where
// the Cell Voltage count=8 expansion occupies bytes 0..15 and the Voltage
// Limit RW signal lives at byte offset 16.
static void emit_2000() {
  uint8_t p[18];
  for (uint8_t i = 0; i < 8; i++) {
    p[i * 2]     = (uint8_t)(cell_mV[i] & 0xFF);
    p[i * 2 + 1] = (uint8_t)((cell_mV[i] >> 8) & 0xFF);
  }
  p[16] = (uint8_t)(voltage_limit_cv & 0xFF);
  p[17] = (uint8_t)((voltage_limit_cv >> 8) & 0xFF);
  sendFrame(0x2000, p, 18);
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

  // Silent mode: suppress all timer-driven emissions until silent_until_ms
  // (data-watchdog test) OR while streaming is explicitly disabled by the
  // host (poll-only cadence test). Inbound poll requests are still gated
  // by silent_until_ms in on_command() but unaffected by streaming_on.
  bool silent = (now < silent_until_ms) || !streaming_on;

  // Stress mode pulls every cadence in by 5x so the host has to keep up
  // with a much faster RX stream + more frequent cycle updates.
  unsigned long iv_1000  = stress_mode_on ?  20 : 100;
  unsigned long iv_2000  = stress_mode_on ? 100 : 500;
  unsigned long iv_3000  = stress_mode_on ?  40 : 200;
  unsigned long iv_cycle = stress_mode_on ? 200 : 1000;

  if (!silent && now - last_1000_ms >= iv_1000) {
    last_1000_ms = now;
    emit_1000();
  }
  if (!silent && now - last_2000_ms >= iv_2000) {
    last_2000_ms = now;
    emit_2000();
  }
  if (!silent && now - last_3000_ms >= iv_3000) {
    last_3000_ms = now;
    emit_3000();
  }

  // Slowly walk telemetry + cycle the bitfield/enum so the UI shows motion.
  if (now - last_cycle_ms >= iv_cycle) {
    last_cycle_ms = now;

    // Pack voltage: 50.00 → 60.00 V then wrap to 40.00 (steps of 0.01 V).
    pack_voltage_cv += 10;
    if (pack_voltage_cv > 6000) pack_voltage_cv = 4000;

    // Pack current: -5.0 → +10.0 A (steps of 0.1 A).
    pack_current_dA += 1;
    if (pack_current_dA > 100) pack_current_dA = -50;

    // Pack SOC: oscillates 70..80%.
    pack_soc_pct = (pack_soc_pct >= 80) ? 70 : (pack_soc_pct + 1);

    // Pack temperature: 20.0 → 30.0 °C.
    pack_temp_dC += 1;
    if (pack_temp_dC > 300) pack_temp_dC = 200;

    // Cell voltage drift: each cell wanders ±5 mV around 3700 so CalcGroups
    // (min/max/avg/diff) has real spread to compute. Uses a tiny per-cell
    // walker so the readings stay correlated frame-to-frame instead of being
    // pure noise.
    for (uint8_t i = 0; i < 8; i++) {
      int16_t delta = ((int16_t)((millis() ^ (i * 17)) & 0x7)) - 3;  // -3..+4 mV
      int32_t next = (int32_t)cell_mV[i] + delta;
      if (next < 3650) next = 3650;
      if (next > 3750) next = 3750;
      cell_mV[i] = (uint16_t)next;
    }

    // Cycle bits: shift the lower 4 status bits, keep "Ready" (bit 7) latched.
    uint8_t low = (status_bits & 0x0F) << 1;
    if (low == 0 || low > 0x0F) low = 0x01;
    status_bits = (status_bits & 0xF0) | low;

    mode = (mode + 1) % 5;                      // 0..4 cycles through Idle..Service
  }
}
