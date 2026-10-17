/*
 * Startup for STM32G474RE: vector table, reset handler (copy .data,
 * zero .bss), default fault handlers.
 */
#include <stdint.h>

extern uint32_t _estack;
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss;

int main(void);
void SystemInit(void);

void Reset_Handler(void);
void Default_Handler(void);
void SysTick_Handler(void);
void LPUART1_IRQHandler(void);

void Reset_Handler(void)
{
    uint32_t *src = &_sidata;
    for (uint32_t *dst = &_sdata; dst < &_edata;)
        *dst++ = *src++;
    for (uint32_t *dst = &_sbss; dst < &_ebss;)
        *dst++ = 0;
    SystemInit();
    main();
    for (;;) {
    }
}

void Default_Handler(void)
{
    /* Unexpected interrupt or fault: stop here (visible in the debugger). */
    for (;;) {
    }
}

#define VECTORS 108U   /* 16 core exceptions + IRQs 0..91 (LPUART1 = 91) */

__attribute__((section(".isr_vector"), used))
void (*const vector_table[VECTORS])(void) = {
    [0]  = (void (*)(void))(&_estack),
    [1]  = Reset_Handler,
    [2]  = Default_Handler,   /* NMI */
    [3]  = Default_Handler,   /* HardFault */
    [4]  = Default_Handler,   /* MemManage */
    [5]  = Default_Handler,   /* BusFault */
    [6]  = Default_Handler,   /* UsageFault */
    [11] = Default_Handler,   /* SVCall */
    [12] = Default_Handler,   /* DebugMon */
    [14] = Default_Handler,   /* PendSV */
    [15] = SysTick_Handler,
    [16 ... 16 + 90] = Default_Handler,   /* every IRQ we do not use */
    [16 + 91] = LPUART1_IRQHandler,
};
