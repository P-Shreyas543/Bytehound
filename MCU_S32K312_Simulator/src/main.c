/*
 * Copyright 2021, 2024 NXP
 * Modified for Bytehound BMS Simulator 2026
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include "drivers.h"

/* ---------- Milliseconds timer using SysTick ---------- */
static volatile uint32_t ms_ticks = 0;

void SysTick_Handler(void)
{
    ms_ticks++;
}

static uint32_t millis(void)
{
    return ms_ticks;
}

/* ---------- CRC16 Modbus (poly 0x8005 reflected, init 0xFFFF) ---------- */
static uint16_t crc16_modbus(const uint8_t *data, uint16_t length)
{
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < length; i++)
    {
        crc ^= data[i];
        for (int j = 0; j < 8; j++)
        {
            crc = (crc & 1) ? ((crc >> 1) ^ 0xA001) : (crc >> 1);
        }
    }
    return crc;
}

/* ---------- Test-hook state ---------- */
static uint8_t  pending_crc_corruptions = 0;
static uint32_t silent_until_ms = 0;
static uint8_t  stress_mode_on = 0;
static uint8_t  streaming_on = 0; // default is false (polling only)

/* ---------- Send one framed packet ---------- */
static void sendFrame(uint16_t frame_id, const uint8_t *payload, uint8_t payload_length)
{
    uint8_t header[5];
    header[0] = 0xAA;
    header[1] = 0x55;
    header[2] = (uint8_t)(frame_id & 0xFF);          // LE low
    header[3] = (uint8_t)((frame_id >> 8) & 0xFF);   // LE high
    header[4] = payload_length;

    LPUART_Wr(LPUART1, header, 5);
    if (payload_length && payload)
    {
        LPUART_Wr(LPUART1, payload, payload_length);
    }

    uint16_t crc = crc16_modbus(header, 5);
    if (payload_length && payload)
    {
        for (uint16_t i = 0; i < payload_length; i++)
        {
            crc ^= payload[i];
            for (int j = 0; j < 8; j++)
            {
                crc = (crc & 1) ? ((crc >> 1) ^ 0xA001) : (crc >> 1);
            }
        }
    }

    if (pending_crc_corruptions > 0)
    {
        crc ^= 0xFF00;  // flip the high byte
        pending_crc_corruptions--;
    }
    uint8_t tail[3] = { (uint8_t)(crc & 0xFF), (uint8_t)((crc >> 8) & 0xFF), 0xEE };
    LPUART_Wr(LPUART1, tail, 3);
}

/* ---------- Telemetry state ---------- */
static uint16_t pack_voltage_cv = 5000;   // 50.00 V (scale 0.01)
static int16_t  pack_current_dA = 20;     // 2.0 A (scale 0.1)
static uint8_t  pack_soc_pct    = 75;     // 75 %
static int16_t  pack_temp_dC    = 250;    // 25.0 C (scale 0.1, offset -40)

static uint16_t cell_mV[8] = { 3700, 3702, 3703, 3699, 3701, 3704, 3700, 3705 };
static uint16_t voltage_limit_cv = 5500;  // 55.00 V (writable, scale 0.01)

static uint8_t  status_bits = 0x81;       // Charging | Ready
static uint8_t  mode        = 1;          // Charging (enum 0..4)

static uint32_t last_1000_ms = 0;
static uint32_t last_2000_ms = 0;
static uint32_t last_3000_ms = 0;
static uint32_t last_cycle_ms = 0;

/* ---------- Telemetry Emitters ---------- */
static void emit_1000(void)
{
    uint8_t p[8] = {
        (uint8_t)(pack_voltage_cv & 0xFF), (uint8_t)((pack_voltage_cv >> 8) & 0xFF),
        (uint8_t)(pack_current_dA & 0xFF), (uint8_t)((pack_current_dA >> 8) & 0xFF),
        pack_soc_pct,
        (uint8_t)(pack_temp_dC & 0xFF),    (uint8_t)((pack_temp_dC >> 8) & 0xFF),
        0x00,  // padding to reach payload_length=8
    };
    sendFrame(0x1000, p, 8);
}

static void emit_2000(void)
{
    uint8_t p[18];
    for (uint8_t i = 0; i < 8; i++)
    {
        p[i * 2]     = (uint8_t)(cell_mV[i] & 0xFF);
        p[i * 2 + 1] = (uint8_t)((cell_mV[i] >> 8) & 0xFF);
    }
    p[16] = (uint8_t)(voltage_limit_cv & 0xFF);
    p[17] = (uint8_t)((voltage_limit_cv >> 8) & 0xFF);
    sendFrame(0x2000, p, 18);
}

static void emit_3000(void)
{
    uint8_t p[2] = { status_bits, mode };
    sendFrame(0x3000, p, 2);
}

/* ---------- Command dispatcher ---------- */
static void on_command(uint16_t frame_id, const uint8_t *payload, uint8_t length)
{
    if (length == 0)
    {
        if (millis() < silent_until_ms) return;
        if (frame_id == 0x1000) { emit_1000(); return; }
        if (frame_id == 0x2000) { emit_2000(); return; }
        if (frame_id == 0x3000) { emit_3000(); return; }
        return;
    }

    if ((frame_id == 0x1000 || frame_id == 0x1001) &&
        length == 2 && payload[0] == 0xFF && payload[1] == 0xFF)
    {
        pack_voltage_cv = 5000;
        pack_current_dA = 20;
        pack_soc_pct = 75;
        pack_temp_dC = 250;
        status_bits = 0x80; // Ready only
        mode = 0;           // Idle
        pending_crc_corruptions = 0;
        silent_until_ms = 0;
        stress_mode_on = 0;
        streaming_on = 1;   // Enable streaming on reset
        return;
    }

    if (frame_id == 0x2000 || frame_id == 0x2001)
    {
        uint16_t requested = 0;
        uint8_t have_request = 0;
        if (length == 2)
        {
            requested = (uint16_t)payload[0] | ((uint16_t)payload[1] << 8);
            have_request = 1;
        }
        else if (length == 18)
        {
            requested = (uint16_t)payload[16] | ((uint16_t)payload[17] << 8);
            have_request = 1;
        }
        if (have_request && requested >= 4000 && requested <= 6000)
        {
            voltage_limit_cv = requested;
            emit_2000();
        }
        return;
    }

    if (frame_id == 0x1002 && length == 1)
    {
        stress_mode_on = (payload[0] != 0);
        return;
    }
    if (frame_id == 0x1003 && length == 1)
    {
        pending_crc_corruptions = payload[0];
        return;
    }
    if (frame_id == 0x1004 && length == 1)
    {
        silent_until_ms = millis() + (uint32_t)payload[0] * 1000UL;
        return;
    }
    if (frame_id == 0x1005 && length == 1)
    {
        streaming_on = (payload[0] == 0);
        return;
    }
}

/* ---------- RX State Machine ---------- */
typedef enum {
    RX_HDR1, RX_HDR2, RX_ID_LO, RX_ID_HI, RX_LEN,
    RX_PAYLOAD, RX_CRC_LO, RX_CRC_HI, RX_FOOTER
} RxState;
static RxState rx_state = RX_HDR1;
static uint16_t rx_frame_id = 0;
static uint8_t  rx_len = 0;
static uint8_t  rx_payload[64];
static uint8_t  rx_idx = 0;
static uint16_t rx_crc_recv = 0;

static void rx_feed(uint8_t b)
{
    switch (rx_state)
    {
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
            if (b == 0xEE)
            {
                uint8_t buf[5 + 64];
                buf[0] = 0xAA; buf[1] = 0x55;
                buf[2] = (uint8_t)(rx_frame_id & 0xFF);
                buf[3] = (uint8_t)((rx_frame_id >> 8) & 0xFF);
                buf[4] = rx_len;
                for (uint8_t i = 0; i < rx_len; i++) buf[5 + i] = rx_payload[i];
                uint16_t crc_calc = crc16_modbus(buf, 5 + rx_len);
                if (crc_calc == rx_crc_recv)
                {
                    on_command(rx_frame_id, rx_payload, rx_len);
                }
            }
            rx_state = RX_HDR1;
            break;
    }
}

int main(void)
{
    /* Disable SWT0 (Watchdog) */
    SWT_0->SR = 0xC520U;
    SWT_0->SR = 0xD928U;
    SWT_0->CR &= ~SWT_CR_WEN_MASK;

    /* Configure clock mode */
    CLOCK_Init(CLOCK_MODE_1_CONFIG);

    /* Enable all on-chip peripherals */
    MCME_PeriphCtrl(MCME_ALL_PERIPH_EN_CONFIG);

    /* Configure PTC6 (LPUART1_RX) and PTC7 (LPUART1_TX) */
    SIUL_Init(PTC, PIN6, INP_ALT6, PIN_UART_MODE_CONFIG);
    SIUL_Init(PTC, PIN7, OUT_ALT2, PIN_UART_MODE_CONFIG);

    /* LPUART1 @ AIPS_SLOW_CLK (12MHz) */
    LPUART_Init(LPUART1, LPUART_INTRMODE_CONFIG(115200, 12000000u));
    /* Override to OSR=12, SBR=8 for high-accuracy 115200 baud (0.16% error) at 12MHz */
    LPUART1->BAUD = (LPUART1->BAUD & ~(LPUART_BAUD_SBR_MASK | LPUART_BAUD_OSR_MASK))
                    | LPUART_BAUD_SBR(8)
                    | LPUART_BAUD_OSR(12);

    /* Disable interrupts on LPUART1 to prevent HardFault on NULL callback */
    LPUART_DisableIrq(LPUART1, LPUART_RIE);

    /* SysTick interrupt every 1ms (Core clock is 24MHz) */
    SysTick_Config(24000000u / 1000u);

    __enable_irq();

    for (;;)
    {
        /* Simple Echo Test */
        while (LPUART_RxFull(LPUART1))
        {
            uint8_t rx_char = (uint8_t)LPUART_GetChar(LPUART1);
            uint8_t *p_rx = &rx_char;
            /* Echo it back */
            LPUART_Wr(LPUART1, p_rx, 1);
        }

        /* Periodically send 'A' every 1000ms */
        static uint32_t last_test_ms = 0;
        uint32_t now = millis();
        if (now - last_test_ms >= 1000)
        {
            last_test_ms = now;
            uint8_t test_char = 'A';
            uint8_t *p_test = &test_char;
            LPUART_Wr(LPUART1, p_test, 1);
        }
    }

    return 0;
}
