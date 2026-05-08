#include <stdint.h>

// ---------------------------------------------------------
// Serial-MonitorApp Compatible Firmware
// Protocol: AA 55 | Frame ID (2) | Length (1) | Payload | CRC16 (2) | EE
// ---------------------------------------------------------

// Computes CRC16 Modbus (Polynomial 0x8005, Reflected, Init 0xFFFF)
uint16_t crc16_modbus(const uint8_t *data, uint16_t length) {
  uint16_t crc = 0xFFFF;
  for (uint16_t i = 0; i < length; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      if (crc & 1) {
        crc = (crc >> 1) ^ 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

// Helper to send a framed packet compatible with the Default protocol
void sendFrame(uint16_t frame_id, uint8_t *payload, uint8_t payload_length) {
  // 1. Header (AA 55)
  // 2. Frame ID (2 bytes, little-endian)
  // 3. Payload Length (1 byte)
  // 4. Payload (N bytes)
  
  uint8_t header[5];
  header[0] = 0xAA;
  header[1] = 0x55;
  header[2] = (frame_id & 0xFF);         // Frame ID low byte
  header[3] = ((frame_id >> 8) & 0xFF);  // Frame ID high byte
  header[4] = payload_length;            // Payload length

  // Send Header and length
  Serial.write(header, 5);
  
  // Send Payload
  if (payload_length > 0 && payload != nullptr) {
    Serial.write(payload, payload_length);
  }

  // Calculate CRC over header[0..4] + payload
  uint16_t crc = 0xFFFF;
  crc = crc16_modbus(header, 5);
  if (payload_length > 0 && payload != nullptr) {
    // Continue CRC calculation with payload
    for (uint16_t i = 0; i < payload_length; i++) {
      crc ^= payload[i];
      for (int j = 0; j < 8; j++) {
        if (crc & 1) {
          crc = (crc >> 1) ^ 0xA001;
        } else {
          crc >>= 1;
        }
      }
    }
  }

  // Send CRC (little-endian: low byte first)
  uint8_t crc_bytes[2];
  crc_bytes[0] = (crc & 0xFF);
  crc_bytes[1] = ((crc >> 8) & 0xFF);
  Serial.write(crc_bytes, 2);

  // Send Footer (EE)
  Serial.write(0xEE);
}

// Variables we want to send
uint16_t simulated_voltage = 500; // 50.0V (Scale 0.1)
int16_t simulated_current = 20;   // 2.0A  (Scale 0.1)
uint16_t voltage_limit = 550;     // 55.0V (Scale 0.1)

unsigned long lastSendTime = 0;

void setup() {
  // Start Serial at 115200 baud
  Serial.begin(115200);
}

void loop() {
  // Send telemetry every 100ms
  if (millis() - lastSendTime >= 100) {
    lastSendTime = millis();

    // -- Frame 0x1000: BMS Status (Voltage and Current) --
    // Total 4 bytes (2 bytes Voltage + 2 bytes Current)
    uint8_t status_payload[4];
    
    // Little Endian encoding
    status_payload[0] = (simulated_voltage & 0xFF);
    status_payload[1] = ((simulated_voltage >> 8) & 0xFF);
    status_payload[2] = (simulated_current & 0xFF);
    status_payload[3] = ((simulated_current >> 8) & 0xFF);
    
    sendFrame(0x1000, status_payload, 4);

    // -- Frame 0x2000: BMS Settings (Voltage Limit) --
    uint8_t settings_payload[2];
    settings_payload[0] = (voltage_limit & 0xFF);
    settings_payload[1] = ((voltage_limit >> 8) & 0xFF);
    
    sendFrame(0x2000, settings_payload, 2);

    // Simulate some simple changes over time
    simulated_voltage += 1;
    if (simulated_voltage > 42) {
      simulated_voltage = 3.65;
    }
    
    simulated_current += 1;
    if (simulated_current > 100) {
      simulated_current = -50;
    }
  }
}
