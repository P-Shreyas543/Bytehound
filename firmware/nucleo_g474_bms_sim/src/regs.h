/*
 * Minimal STM32G474 register definitions — only what this firmware uses.
 * Addresses and bit positions from RM0440 (STM32G4 reference manual).
 * Kept self-contained so the project builds with just arm-none-eabi-gcc
 * (no STM32CubeG4 package needed).
 */
#ifndef REGS_H
#define REGS_H

#include <stdint.h>

#define REG32(addr) (*(volatile uint32_t *)(addr))

/* ---- RCC (0x4002 1000) ------------------------------------------------ */
#define RCC_BASE        0x40021000UL
#define RCC_CR          REG32(RCC_BASE + 0x00)
#define RCC_CFGR        REG32(RCC_BASE + 0x08)
#define RCC_PLLCFGR     REG32(RCC_BASE + 0x0C)
#define RCC_AHB2ENR     REG32(RCC_BASE + 0x4C)
#define RCC_APB1ENR1    REG32(RCC_BASE + 0x58)
#define RCC_APB1ENR2    REG32(RCC_BASE + 0x5C)
#define RCC_CCIPR       REG32(RCC_BASE + 0x88)

#define RCC_CR_HSION            (1UL << 8)
#define RCC_CR_HSIRDY           (1UL << 10)
#define RCC_CR_PLLON            (1UL << 24)
#define RCC_CR_PLLRDY           (1UL << 25)
#define RCC_CFGR_SW_MASK        (3UL << 0)
#define RCC_CFGR_SW_PLL         (3UL << 0)
#define RCC_CFGR_SWS_MASK       (3UL << 2)
#define RCC_CFGR_SWS_PLL        (3UL << 2)
#define RCC_CFGR_HPRE_MASK      (0xFUL << 4)
#define RCC_CFGR_HPRE_DIV2      (0x8UL << 4)
#define RCC_PLLCFGR_SRC_HSI     (2UL << 0)
#define RCC_PLLCFGR_M(m)        (((uint32_t)(m) - 1U) << 4)
#define RCC_PLLCFGR_N(n)        ((uint32_t)(n) << 8)
#define RCC_PLLCFGR_REN         (1UL << 24)
#define RCC_PLLCFGR_R_DIV2      (0UL << 25)
#define RCC_AHB2ENR_GPIOAEN     (1UL << 0)
#define RCC_APB1ENR1_PWREN      (1UL << 28)
#define RCC_APB1ENR2_LPUART1EN  (1UL << 0)
#define RCC_CCIPR_LPUART1SEL_MASK (3UL << 10)
#define RCC_CCIPR_LPUART1SEL_HSI  (2UL << 10)

/* ---- FLASH (0x4002 2000) ---------------------------------------------- */
#define FLASH_BASE      0x40022000UL
#define FLASH_ACR       REG32(FLASH_BASE + 0x00)
#define FLASH_ACR_LATENCY_MASK  (0xFUL << 0)
#define FLASH_ACR_PRFTEN        (1UL << 8)
#define FLASH_ACR_ICEN          (1UL << 9)
#define FLASH_ACR_DCEN          (1UL << 10)

/* ---- GPIOA (0x4800 0000) ---------------------------------------------- */
#define GPIOA_BASE      0x48000000UL
#define GPIOA_MODER     REG32(GPIOA_BASE + 0x00)
#define GPIOA_OSPEEDR   REG32(GPIOA_BASE + 0x08)
#define GPIOA_PUPDR     REG32(GPIOA_BASE + 0x0C)
#define GPIOA_BSRR      REG32(GPIOA_BASE + 0x18)
#define GPIOA_AFRL      REG32(GPIOA_BASE + 0x20)

/* ---- LPUART1 (0x4000 8000): ST-LINK virtual COM port on PA2/PA3 ------- */
#define LPUART1_BASE    0x40008000UL
#define LPUART1_CR1     REG32(LPUART1_BASE + 0x00)
#define LPUART1_CR2     REG32(LPUART1_BASE + 0x04)
#define LPUART1_CR3     REG32(LPUART1_BASE + 0x08)
#define LPUART1_BRR     REG32(LPUART1_BASE + 0x0C)
#define LPUART1_ISR     REG32(LPUART1_BASE + 0x1C)
#define LPUART1_ICR     REG32(LPUART1_BASE + 0x20)
#define LPUART1_RDR     REG32(LPUART1_BASE + 0x24)
#define LPUART1_TDR     REG32(LPUART1_BASE + 0x28)
#define LPUART1_PRESC   REG32(LPUART1_BASE + 0x2C)

#define USART_CR1_UE        (1UL << 0)
#define USART_CR1_RE        (1UL << 2)
#define USART_CR1_TE        (1UL << 3)
#define USART_CR1_RXNEIE    (1UL << 5)
#define USART_CR1_FIFOEN    (1UL << 29)
#define USART_CR3_EIE       (1UL << 0)
#define USART_ISR_PE        (1UL << 0)
#define USART_ISR_FE        (1UL << 1)
#define USART_ISR_NE        (1UL << 2)
#define USART_ISR_ORE       (1UL << 3)
#define USART_ISR_RXNE      (1UL << 5)
#define USART_ISR_TC        (1UL << 6)
#define USART_ISR_TXE       (1UL << 7)
#define USART_ICR_PECF      (1UL << 0)
#define USART_ICR_FECF      (1UL << 1)
#define USART_ICR_NECF      (1UL << 2)
#define USART_ICR_ORECF     (1UL << 3)

#define LPUART1_IRQn    91U

/* ---- Cortex-M4 core --------------------------------------------------- */
#define SYST_CSR        REG32(0xE000E010UL)
#define SYST_RVR        REG32(0xE000E014UL)
#define SYST_CVR        REG32(0xE000E018UL)
#define NVIC_ISER(n)    REG32(0xE000E100UL + 4U * (n))
#define SCB_AIRCR       REG32(0xE000ED0CUL)
#define SCB_AIRCR_RESET ((0x5FAUL << 16) | (1UL << 2))

#endif /* REGS_H */
