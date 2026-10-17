/*
 * Bytehound BMS simulator + hardware-in-the-loop (HIL) test firmware
 * for the NUCLEO-G474RE.
 *
 * Talks to the PC over the ST-LINK virtual COM port (LPUART1, PA2/PA3).
 *
 * 1. A faithful port of MCU_BMS_Simulator.ino (Arduino), so the app's
 *    bundled config (app/resources/config_template) and smoke_headless.py
 *    work against this board unchanged:
 *      RX 0x1000 BMS_Status (8 B), 0x2000 BMS_Settings (18 B),
 *         0x3000 Status_Flags (2 B); empty-payload frames are polls.
 *      TX 0x1000 FF FF Reset Faults; 0x2000 / 0x2001 Voltage Limit write;
 *         0x1002 stress mode, 0x1003 inject N CRC errors, 0x1004 go silent,
 *         0x1005 streaming off/on (default off, as in the sketch).
 *
 * 2. HIL extensions on IDs the app config does not use (0x7Fxx, 0x4000).
 *    The board counts exactly what it sent, so the PC can prove zero loss:
 *      0x4000 HIL_Counter  (board -> PC) u32 seq, u32 uptime_ms
 *      0x7F01 STREAM       u16 cycles_per_s (0 = stop), u8 flags
 *                          (bit0: add 0x4000 counter frame to each cycle)
 *                          A cycle = 0x1000, 0x2000, 0x3000 [, 0x4000].
 *      0x7F02 SET_BAUD     u32 baud  -> ack 0x7F82 at the old baud, then switch
 *      0x7F03 INJECT       u16 noise_every_n_frames, u16 corrupt_every_n_frames
 *                          (0 = off). Noise = 00 AA 13 77; corrupt = CRC hi ^ FF
 *      0x7F04 RESET_STATS  zero all counters and the counter sequence
 *      0x7F05 GET_STATS    -> 0x7F85: 15 x u32 (see send_stats())
 *      0x7F06 BURST        u32 cycles: send that many cycles (with 0x4000) back to back
 *      0x7F07 PING         -> 0x7F87: firmware version text
 *    Replies (0x7F8x) are not counted in the telemetry statistics.
 *
 * Frame format (as the app config): AA 55 | id LE16 | len u8 | payload |
 * CRC16-Modbus LE over header..payload | EE.
 */
#include <stdint.h>
#include <string.h>
#include "regs.h"

#define FW_VERSION  "bh-sim-g474 1.0.0"
#define HSI_HZ      16000000UL
#define SYSCLK_HZ   150000000UL

/* ===================================================================== */
/* Clock, tick, GPIO                                                      */
/* ===================================================================== */

static volatile uint32_t g_ms;

void SysTick_Handler(void) { g_ms++; }
static inline uint32_t millis(void) { return g_ms; }

void SystemInit(void)
{
    /* 4 flash wait states + caches before raising the clock (<= 150 MHz,
       voltage range 1 normal mode, the reset default). */
    FLASH_ACR = (FLASH_ACR & ~FLASH_ACR_LATENCY_MASK) | 4U |
                FLASH_ACR_PRFTEN | FLASH_ACR_ICEN | FLASH_ACR_DCEN;
    while ((FLASH_ACR & FLASH_ACR_LATENCY_MASK) != 4U) {
    }
    RCC_CR |= RCC_CR_HSION;
    while (!(RCC_CR & RCC_CR_HSIRDY)) {
    }
    /* HSI16 / M4 = 4 MHz, x N75 = 300 MHz VCO, / R2 = 150 MHz. */
    RCC_PLLCFGR = RCC_PLLCFGR_SRC_HSI | RCC_PLLCFGR_M(4) | RCC_PLLCFGR_N(75) |
                  RCC_PLLCFGR_REN | RCC_PLLCFGR_R_DIV2;
    RCC_CR |= RCC_CR_PLLON;
    while (!(RCC_CR & RCC_CR_PLLRDY)) {
    }
    /* RM0440: step through AHB/2 when switching above 80 MHz. */
    RCC_CFGR = (RCC_CFGR & ~RCC_CFGR_HPRE_MASK) | RCC_CFGR_HPRE_DIV2;
    RCC_CFGR = (RCC_CFGR & ~RCC_CFGR_SW_MASK) | RCC_CFGR_SW_PLL;
    while ((RCC_CFGR & RCC_CFGR_SWS_MASK) != RCC_CFGR_SWS_PLL) {
    }
    for (volatile uint32_t i = 0; i < 200U; i++) {
    }
    RCC_CFGR &= ~RCC_CFGR_HPRE_MASK;
}

static void systick_init(void)
{
    SYST_RVR = SYSCLK_HZ / 1000U - 1U;
    SYST_CVR = 0;
    SYST_CSR = 7U;   /* processor clock, interrupt, enable */
}

static void gpio_init(void)
{
    RCC_AHB2ENR |= RCC_AHB2ENR_GPIOAEN;
    (void)RCC_AHB2ENR;
    /* PA2 / PA3 = AF12 (LPUART1 TX / RX), PA5 = LD2 output. */
    GPIOA_MODER = (GPIOA_MODER & ~((3U << 4) | (3U << 6) | (3U << 10))) |
                  (2U << 4) | (2U << 6) | (1U << 10);
    GPIOA_AFRL = (GPIOA_AFRL & ~((0xFU << 8) | (0xFU << 12))) | (12U << 8) | (12U << 12);
    GPIOA_OSPEEDR |= (3U << 4) | (3U << 6);
    GPIOA_PUPDR = (GPIOA_PUPDR & ~(3U << 6)) | (1U << 6);   /* RX pull-up */
}

static void led(int on) { GPIOA_BSRR = on ? (1U << 5) : (1U << 21); }

/* ===================================================================== */
/* LPUART1 + statistics                                                   */
/* ===================================================================== */

#define RX_RING 2048U
static volatile uint8_t  rx_ring[RX_RING];
static volatile uint16_t rx_head, rx_tail;

static struct {
    uint32_t frames[5];        /* 0x1000, 0x2000, 0x3000, 0x4000, other */
    uint32_t corrupted;        /* frames sent with a deliberately bad CRC */
    uint32_t noise_bytes;      /* injected noise bytes */
    uint32_t tx_bytes;         /* all bytes sent except control replies */
    uint32_t rx_frames_ok;
    uint32_t rx_crc_errors;
    volatile uint32_t rx_overruns;
    volatile uint32_t rx_ring_full;
    volatile uint32_t rx_line_errors;
} st;

static uint32_t g_baud = 115200U;

void LPUART1_IRQHandler(void)
{
    uint32_t isr = LPUART1_ISR;
    if (isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE | USART_ISR_PE)) {
        if (isr & USART_ISR_ORE)
            st.rx_overruns++;
        else
            st.rx_line_errors++;
        LPUART1_ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF | USART_ICR_PECF;
    }
    while (LPUART1_ISR & USART_ISR_RXNE) {
        uint8_t b = (uint8_t)LPUART1_RDR;
        uint16_t next = (uint16_t)((rx_head + 1U) % RX_RING);
        if (next != rx_tail) {
            rx_ring[rx_head] = b;
            rx_head = next;
        } else {
            st.rx_ring_full++;
        }
    }
}

static void lpuart_set_baud(uint32_t baud)
{
    while (!(LPUART1_ISR & USART_ISR_TC)) {
    }
    LPUART1_CR1 &= ~USART_CR1_UE;
    /* LPUART: BRR = 256 * fck / baud, fck = HSI16 (exact for every rate). */
    LPUART1_BRR = (uint32_t)(((uint64_t)HSI_HZ * 256U + baud / 2U) / baud);
    LPUART1_CR1 |= USART_CR1_UE;
    g_baud = baud;
}

static void lpuart_init(uint32_t baud)
{
    RCC_APB1ENR2 |= RCC_APB1ENR2_LPUART1EN;
    (void)RCC_APB1ENR2;
    RCC_CCIPR = (RCC_CCIPR & ~RCC_CCIPR_LPUART1SEL_MASK) | RCC_CCIPR_LPUART1SEL_HSI;
    LPUART1_CR1 = 0;
    LPUART1_PRESC = 0;
    LPUART1_BRR = (uint32_t)(((uint64_t)HSI_HZ * 256U + baud / 2U) / baud);
    LPUART1_CR3 = USART_CR3_EIE;
    LPUART1_CR1 = USART_CR1_FIFOEN | USART_CR1_RXNEIE | USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
    g_baud = baud;
    NVIC_ISER(LPUART1_IRQn / 32U) = 1UL << (LPUART1_IRQn % 32U);
}

static int g_counting = 1;   /* 0 while sending control replies */

static void tx_byte(uint8_t b)
{
    while (!(LPUART1_ISR & USART_ISR_TXE)) {
    }
    LPUART1_TDR = b;
    if (g_counting)
        st.tx_bytes++;
}

/* ===================================================================== */
/* CRC16 Modbus (poly 0xA001 reflected, init 0xFFFF), table driven        */
/* ===================================================================== */

static uint16_t crc_table[256];

static void crc_init(void)
{
    for (uint32_t i = 0; i < 256U; i++) {
        uint16_t c = (uint16_t)i;
        for (int j = 0; j < 8; j++)
            c = (c & 1U) ? (uint16_t)((c >> 1) ^ 0xA001U) : (uint16_t)(c >> 1);
        crc_table[i] = c;
    }
}

static uint16_t crc_update(uint16_t crc, const uint8_t *d, uint32_t n)
{
    while (n--)
        crc = (uint16_t)((crc >> 8) ^ crc_table[(crc ^ *d++) & 0xFFU]);
    return crc;
}

/* ===================================================================== */
/* Framing, test hooks                                                    */
/* ===================================================================== */

static uint8_t  pending_crc_corruptions;   /* 0x1003 */
static uint32_t silent_until_ms;           /* 0x1004 */
static int      stress_mode_on;            /* 0x1002 */
static int      streaming_on;              /* 0x1005, default off as in the sketch */

static uint16_t hil_noise_every, hil_corrupt_every;
static uint32_t hil_frames_since_noise, hil_frames_since_corrupt;

static int frame_index(uint16_t id)
{
    switch (id) {
    case 0x1000: return 0;
    case 0x2000: return 1;
    case 0x3000: return 2;
    case 0x4000: return 3;
    default:     return 4;
    }
}

static void send_frame(uint16_t id, const uint8_t *payload, uint8_t len)
{
    uint8_t hdr[5] = { 0xAA, 0x55, (uint8_t)(id & 0xFFU), (uint8_t)(id >> 8), len };
    uint16_t crc = crc_update(0xFFFFU, hdr, 5);
    crc = crc_update(crc, payload, len);
    int corrupt = 0;
    if (g_counting) {
        if (pending_crc_corruptions) {
            pending_crc_corruptions--;
            corrupt = 1;
        }
        if (hil_corrupt_every && ++hil_frames_since_corrupt >= hil_corrupt_every) {
            hil_frames_since_corrupt = 0;
            corrupt = 1;
        }
    }
    if (corrupt)
        crc ^= 0xFF00U;
    for (int i = 0; i < 5; i++)
        tx_byte(hdr[i]);
    for (uint8_t i = 0; i < len; i++)
        tx_byte(payload[i]);
    tx_byte((uint8_t)(crc & 0xFFU));
    tx_byte((uint8_t)(crc >> 8));
    tx_byte(0xEE);
    if (!g_counting)
        return;
    if (corrupt)
        st.corrupted++;
    else
        st.frames[frame_index(id)]++;
    if (hil_noise_every && ++hil_frames_since_noise >= hil_noise_every) {
        static const uint8_t noise[4] = { 0x00, 0xAA, 0x13, 0x77 };
        hil_frames_since_noise = 0;
        for (int i = 0; i < 4; i++)
            tx_byte(noise[i]);
        st.noise_bytes += 4U;
    }
}

static void send_control(uint16_t id, const uint8_t *payload, uint8_t len)
{
    g_counting = 0;
    send_frame(id, payload, len);
    g_counting = 1;
}

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static uint32_t get_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* ===================================================================== */
/* Telemetry (ported from MCU_BMS_Simulator.ino)                          */
/* ===================================================================== */

static uint16_t pack_voltage_cv = 5000;
static int16_t  pack_current_dA = 20;
static uint8_t  pack_soc_pct    = 75;
static int16_t  pack_temp_dC    = 250;
static uint16_t cell_mV[8] = { 3700, 3702, 3703, 3699, 3701, 3704, 3700, 3705 };
static uint16_t voltage_limit_cv = 5500;
static uint8_t  status_bits = 0x81;
static uint8_t  mode = 1;
static uint32_t hil_seq;

static void emit_1000(void)
{
    uint8_t p[8] = {
        (uint8_t)(pack_voltage_cv & 0xFF), (uint8_t)(pack_voltage_cv >> 8),
        (uint8_t)(pack_current_dA & 0xFF), (uint8_t)((uint16_t)pack_current_dA >> 8),
        pack_soc_pct,
        (uint8_t)(pack_temp_dC & 0xFF), (uint8_t)((uint16_t)pack_temp_dC >> 8),
        0x00,
    };
    send_frame(0x1000, p, 8);
}

static void emit_2000(void)
{
    uint8_t p[18];
    for (int i = 0; i < 8; i++) {
        p[i * 2] = (uint8_t)(cell_mV[i] & 0xFF);
        p[i * 2 + 1] = (uint8_t)(cell_mV[i] >> 8);
    }
    p[16] = (uint8_t)(voltage_limit_cv & 0xFF);
    p[17] = (uint8_t)(voltage_limit_cv >> 8);
    send_frame(0x2000, p, 18);
}

static void emit_3000(void)
{
    uint8_t p[2] = { status_bits, mode };
    send_frame(0x3000, p, 2);
}

static void emit_4000(void)
{
    uint8_t p[8];
    put_u32(p, hil_seq++);
    put_u32(p + 4, millis());
    send_frame(0x4000, p, 8);
}

static void walk_telemetry(void)
{
    pack_voltage_cv += 10;
    if (pack_voltage_cv > 6000) pack_voltage_cv = 4000;
    pack_current_dA += 1;
    if (pack_current_dA > 100) pack_current_dA = -50;
    pack_soc_pct = (pack_soc_pct >= 80) ? 70 : (uint8_t)(pack_soc_pct + 1);
    pack_temp_dC += 1;
    if (pack_temp_dC > 300) pack_temp_dC = 200;
    for (int i = 0; i < 8; i++) {
        int32_t delta = (int32_t)((millis() ^ (uint32_t)(i * 17)) & 0x7U) - 3;
        int32_t next = (int32_t)cell_mV[i] + delta;
        if (next < 3650) next = 3650;
        if (next > 3750) next = 3750;
        cell_mV[i] = (uint16_t)next;
    }
    uint8_t low = (uint8_t)((status_bits & 0x0F) << 1);
    if (low == 0 || low > 0x0F) low = 0x01;
    status_bits = (uint8_t)((status_bits & 0xF0) | low);
    mode = (uint8_t)((mode + 1U) % 5U);
}

/* ===================================================================== */
/* HIL state                                                              */
/* ===================================================================== */

static uint16_t hil_rate;              /* cycles per second, 0 = off */
static int      hil_with_counter;
static uint32_t hil_stream_t0, hil_stream_sent;
static uint32_t hil_burst_left;

static void emit_cycle(void)
{
    emit_1000();
    emit_2000();
    emit_3000();
    if (hil_with_counter)
        emit_4000();
}

static void send_stats(void)
{
    uint8_t p[15 * 4];
    uint32_t v[15] = {
        st.frames[0], st.frames[1], st.frames[2], st.frames[3],
        st.corrupted, st.noise_bytes, st.tx_bytes,
        st.rx_frames_ok, st.rx_crc_errors, st.rx_overruns, st.rx_ring_full, st.rx_line_errors,
        millis(), hil_seq, g_baud,
    };
    for (int i = 0; i < 15; i++)
        put_u32(p + 4 * i, v[i]);
    send_control(0x7F85, p, sizeof p);
}

/* ===================================================================== */
/* Commands                                                               */
/* ===================================================================== */

static void on_command(uint16_t id, const uint8_t *p, uint8_t len)
{
    /* Empty payload on a telemetry ID = poll request. (Other empty-payload
       frames, e.g. PING / GET_STATS, fall through to their handlers.) */
    if (len == 0 && (id == 0x1000 || id == 0x2000 || id == 0x3000 || id == 0x4000)) {
        if ((int32_t)(millis() - silent_until_ms) < 0) return;
        if (id == 0x1000) emit_1000();
        else if (id == 0x2000) emit_2000();
        else if (id == 0x3000) emit_3000();
        else emit_4000();
        return;
    }
    if ((id == 0x1000 || id == 0x1001) && len == 2 && p[0] == 0xFF && p[1] == 0xFF) {
        pack_voltage_cv = 5000; pack_current_dA = 20; pack_soc_pct = 75; pack_temp_dC = 250;
        status_bits = 0x80; mode = 0;
        pending_crc_corruptions = 0; silent_until_ms = millis();
        stress_mode_on = 0; streaming_on = 1;
        return;
    }
    if (id == 0x2000 || id == 0x2001) {
        uint16_t req = 0;
        int have = 0;
        if (len == 2) { req = (uint16_t)(p[0] | (p[1] << 8)); have = 1; }
        else if (len == 18) { req = (uint16_t)(p[16] | (p[17] << 8)); have = 1; }
        if (have && req >= 4000 && req <= 6000) {
            voltage_limit_cv = req;
            emit_2000();
        }
        return;
    }
    if (id == 0x1002 && len == 1) { stress_mode_on = (p[0] != 0); return; }
    if (id == 0x1003 && len == 1) { pending_crc_corruptions = p[0]; return; }
    if (id == 0x1004 && len == 1) { silent_until_ms = millis() + (uint32_t)p[0] * 1000U; return; }
    if (id == 0x1005 && len == 1) { streaming_on = (p[0] == 0); return; }

    /* ---- HIL extensions ---- */
    if (id == 0x7F01 && len >= 2) {
        hil_rate = (uint16_t)(p[0] | (p[1] << 8));
        hil_with_counter = (len >= 3) ? (p[2] & 1U) : 1;
        hil_stream_t0 = millis();
        hil_stream_sent = 0;
        return;
    }
    if (id == 0x7F02 && len == 4) {
        uint32_t baud = get_u32(p);
        if (baud >= 9600U && baud <= 5000000U) {
            uint8_t ack[4];
            put_u32(ack, baud);
            send_control(0x7F82, ack, 4);
            lpuart_set_baud(baud);
        }
        return;
    }
    if (id == 0x7F03 && len == 4) {
        hil_noise_every = (uint16_t)(p[0] | (p[1] << 8));
        hil_corrupt_every = (uint16_t)(p[2] | (p[3] << 8));
        hil_frames_since_noise = hil_frames_since_corrupt = 0;
        return;
    }
    if (id == 0x7F04) {
        memset(&st, 0, sizeof st);
        hil_seq = 0;
        return;
    }
    if (id == 0x7F05) { send_stats(); return; }
    if (id == 0x7F06 && len == 4) { hil_with_counter = 1; hil_burst_left = get_u32(p); return; }
    if (id == 0x7F07) {
        send_control(0x7F87, (const uint8_t *)FW_VERSION, (uint8_t)strlen(FW_VERSION));
        return;
    }
}

/* AA 55 | id LE | len | payload | crc LE | EE  (validated, then dispatched) */
static void rx_feed(uint8_t b)
{
    static enum { H1, H2, IDL, IDH, LEN, PAY, CL, CH, FT } s = H1;
    static uint8_t buf[5 + 255];
    static uint8_t idx, plen;
    static uint16_t crc_rx;
    switch (s) {
    case H1: if (b == 0xAA) { buf[0] = b; s = H2; } break;
    case H2: if (b == 0x55) { buf[1] = b; s = IDL; } else s = (b == 0xAA) ? H2 : H1; break;
    case IDL: buf[2] = b; s = IDH; break;
    case IDH: buf[3] = b; s = LEN; break;
    case LEN: buf[4] = plen = b; idx = 0; s = plen ? PAY : CL; break;
    case PAY: buf[5 + idx++] = b; if (idx >= plen) s = CL; break;
    case CL: crc_rx = b; s = CH; break;
    case CH: crc_rx |= (uint16_t)(b << 8); s = FT; break;
    case FT:
        if (b == 0xEE && crc_update(0xFFFFU, buf, 5U + plen) == crc_rx) {
            st.rx_frames_ok++;
            on_command((uint16_t)(buf[2] | (buf[3] << 8)), buf + 5, plen);
        } else {
            st.rx_crc_errors++;
        }
        s = H1;
        break;
    }
}

static void process_rx(void)
{
    while (rx_tail != rx_head) {
        uint8_t b = rx_ring[rx_tail];
        rx_tail = (uint16_t)((rx_tail + 1U) % RX_RING);
        rx_feed(b);
    }
}

/* ===================================================================== */
/* Main loop                                                              */
/* ===================================================================== */

int main(void)
{
    gpio_init();
    crc_init();
    systick_init();
    lpuart_init(115200U);

    uint32_t last_1000 = 0, last_2000 = 0, last_3000 = 0, last_cycle = 0, last_led = 0;
    int led_on = 0;

    for (;;) {
        process_rx();
        uint32_t now = millis();
        int silent = ((int32_t)(now - silent_until_ms) < 0) || !streaming_on;

        uint32_t iv_1000 = stress_mode_on ? 20U : 100U;
        uint32_t iv_2000 = stress_mode_on ? 100U : 500U;
        uint32_t iv_3000 = stress_mode_on ? 40U : 200U;
        uint32_t iv_cycle = stress_mode_on ? 200U : 1000U;

        if (!silent && now - last_1000 >= iv_1000) { last_1000 = now; emit_1000(); }
        if (!silent && now - last_2000 >= iv_2000) { last_2000 = now; emit_2000(); }
        if (!silent && now - last_3000 >= iv_3000) { last_3000 = now; emit_3000(); }
        if (now - last_cycle >= iv_cycle) { last_cycle = now; walk_telemetry(); }

        /* HIL stream: send every cycle that is due, catching up after RX work. */
        if (hil_rate) {
            uint32_t due = (uint32_t)(((uint64_t)(millis() - hil_stream_t0) * hil_rate) / 1000U);
            while (hil_stream_sent < due && hil_rate) {
                emit_cycle();
                hil_stream_sent++;
                process_rx();
            }
        }
        /* HIL burst: back to back at full line rate. */
        while (hil_burst_left) {
            emit_cycle();
            hil_burst_left--;
            process_rx();
        }

        uint32_t blink = (hil_rate || streaming_on) ? 100U : 500U;
        if (now - last_led >= blink) {
            last_led = now;
            led_on = !led_on;
            led(led_on);
        }
    }
}
