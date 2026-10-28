/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      mcme.h
 * @brief     Mode Entry Module (MCME) driver header file.
 */
#ifndef __MCME_H
#define __MCME_H

#include "mcme_private.h"     /* include private definitions                  */

extern const uint32_t coreid_pidx[];
extern const uint32_t coreid_cidx[];

/******************************************************************************
 * Configuration structure definitions                                        *
 ******************************************************************************/
typedef struct
{
  uint32_t PRTN0_COFB1; ///< AIPS_0 IPS slot numbers 32 - 47
  uint32_t PRTN1_COFB0; ///< AIPS_1 IPS slot numbers 0 - 31
  uint32_t PRTN1_COFB1; ///< AIPS_1 IPS slot numbers 32 - 63
  uint32_t PRTN1_COFB2; ///< AIPS_1 IPS slot numbers 64 - 95
  uint32_t PRTN1_COFB3; ///< AIPS_1 IPS slot numbers 96 - 109
  uint32_t PRTN2_COFB0; ///< AIPS_2 IPS slot numbers 0 - 31
  uint32_t PRTN2_COFB1; ///< AIPS_2 IPS slot numbers 31 - 59
} tMCME;

/******************************************************************************
* Device requests
*
*//*! @addtogroup device_resets
* @{
*******************************************************************************/
#define MCME_DEST_RST_REQ (uint32_t)(1UL << 0)  ///< Destructive reset request
#define MCME_FUNC_RST_REQ (uint32_t)(1UL << 1)  ///< Functional reset request
/*! @} End of device_resets                                                   */

/******************************************************************************
* Core enumeration
*
*//*! @addtogroup core_list
* @{
*******************************************************************************/
#define MCME_CORE0 (uint32_t)(1UL << 0) ///< Cortex-M7 0 master core (boot core)
#define MCME_CORE1 (uint32_t)(1UL << 1) ///< Cortex-M7 1 partner core
/*! @} End of core_list                                                       */

/******************************************************************************
* MCME module clock configurations
*
*//*! @addtogroup mcme_config
* @{
* This table lists on-chip peripherals, control symbols and state of peripheral after reset. 
* Each peripheral with control symbol can be enabled or disabled during application initialization
* by applying <c>SET</c> or <c>CLR</c> macro on its control symbol within configuration structure. 
* Default configuration structures are described below. Create new configuration structure using 
* steps in section: @ref config_struct_macros "Creating Configuration Structure". 
*|                   On-chip peripheral                     | Control symbol | Reset state |S32K312|
*|:--------------------------------------------------------:|:--------------:|:-----------:|:-----:|
*|                    Trigger Multiplexer                   |   MCME_TRGMUX  |      -      |X      |
*|                Body Cross Triggering Unit                |    MCME_BCTU   |      -      |X      |
*|                          EMIOS 0                         |   MCME_EMIOS0  |      -      |X      |
*|                          EMIOS 1                         |   MCME_EMIOS1  |      -      |X      |
*|                          EMIOS 2                         |   MCME_EMIOS2  |      -      |-      |
*|                   Logic Control Unit 0                   |    MCME_LCU0   |      -      |X      |
*|                   Logic Control Unit 1                   |    MCME_LCU1   |      -      |X      |
*|               Analog-to-digital converter 0              |    MCME_ADC0   |      -      |X      |
*|               Analog-to-digital converter 1              |    MCME_ADC1   |      -      |X      |
*|               Analog-to-digital converter 2              |    MCME_ADC2   |      -      |-      |
*|              Programmable Interrupt Timer 0              |    MCME_PIT0   |   Enabled   |X      |
*|              Programmable Interrupt Timer 1              |    MCME_PIT1   |      -      |X      |
*|                           MU_A                           |    MCME_MUA    |      -      |-      |
*|                           MU_B                           |    MCME_MUB    |      -      |-      |
*|                           I3C0                           |    MCME_I3C0   |      -      |X      |
*|                  System crossbar switch                  |        -       |   Enabled   |X      |
*|  Crossbar Integrity Checker   (System AXBS / AXBS Lite)  |        -       |   Enabled   |X      |
*|    Crossbar Integrity Checker   (Peripheral AXBS-Lite)   |        -       |   Enabled   |X      |
*|      EDMA control & status   (MP_CSR; MP_ES; MP_HRS)     |    MCME_EDMA   |      -      |X      |
*|           EDMA transfer control   descriptor 0           |    MCME_TCD0   |      -      |X      |
*|           EDMA transfer control   descriptor 1           |    MCME_TCD1   |      -      |X      |
*|           EDMA transfer control   descriptor 2           |    MCME_TCD2   |      -      |X      |
*|           EDMA transfer control   descriptor 3           |    MCME_TCD3   |      -      |X      |
*|           EDMA transfer control   descriptor 4           |    MCME_TCD4   |      -      |X      |
*|           EDMA transfer control   descriptor 5           |    MCME_TCD5   |      -      |X      |
*|           EDMA transfer control   descriptor 6           |    MCME_TCD6   |      -      |X      |
*|           EDMA transfer control   descriptor 7           |    MCME_TCD7   |      -      |X      |
*|           EDMA transfer control   descriptor 8           |    MCME_TCD8   |      -      |X      |
*|           EDMA transfer control   descriptor 9           |    MCME_TCD9   |      -      |X      |
*|           EDMA transfer control   descriptor 10          |   MCME_TCD10   |      -      |X      |
*|           EDMA transfer control   descriptor 11          |   MCME_TCD11   |      -      |X      |
*|                      Debug APB Page0                     |        -       |   Enabled   |X      |
*|                      Debug APB Page1                     |        -       |   Enabled   |X      |
*|                      Debug APB Page2                     |        -       |   Enabled   |X      |
*|                      Debug APB Page3                     |        -       |   Enabled   |X      |
*|                   Debug APB Paged Area                   |        -       |   Enabled   |X      |
*|                          SDA-AP                          |    MCME_SDA    |   Enabled   |X      |
*|                            EIM                           |    MCME_EIM    |      -      |X      |
*|                            ERM                           |    MCME_ERM    |      -      |X      |
*|                           MSCM                           |    MCME_MSCM   |      -      |X      |
*|                     RAM controller 0                     |        -       |   Enabled   |X      |
*|                     Flash controller                     |        -       |   Enabled   |X      |
*|                Flash controller alternate                |        -       |   Enabled   |X      |
*|                    Software Watchdog 0                   |    MCME_SWT0   |   Enabled   |X      |
*|                   System Timer Module 0                  |    MCME_STM0   |      -      |X      |
*|                           XRDC                           |        -       |   Enabled   |X      |
*|                     Interrupt Monitor                    |    MCME_INTM   |      -      |X      |
*|                 DMA Channel Multiplexer 0                |  MCME_DMAMUX0  |      -      |X      |
*|                 DMA Channel Multiplexer 1                |  MCME_DMAMUX1  |      -      |X      |
*|                      Real-time clock                     |    MCME_RTC    |   Enabled   |X      |
*|                  Reset Generation Module                 |        -       |   Enabled   |X      |
*|                  SIUL2_VIRTWRAPPER_PDAC0                 |        -       |   Enabled   |X      |
*|                  SIUL2_VIRTWRAPPER_PDAC0                 |        -       |   Enabled   |X      |
*|                  SIUL2_VIRTWRAPPER_PDAC1                 |        -       |   Enabled   |X      |
*|                  SIUL2_VIRTWRAPPER_PDAC1                 |        -       |   Enabled   |X      |
*|                  SIUL2_VIRTWRAPPER_PDAC2                 |        -       |   Enabled   |X      |
*|                  SIUL2_VIRTWRAPPER_PDAC2                 |        -       |   Enabled   |X      |
*|                     SIUL2_VIRTWRAPPER                    |   MCME_VWRAP   |   Enabled   |X      |
*|         System Status and Configuration Module           |        -       |   Enabled   |X      |
*|                        Wakeup Unit                       |    MCME_WKPU   |   Enabled   |X      |
*|                          CMU 0-5                         |   MCME_CMU05   |      -      |X      |
*|            Touch Sensing Coupling   Controller           |    MCME_TSPC   |   Enabled   |X      |
*|           32 kHz Slow Internal RC   Oscillator           |        -       |   Enabled   |X      |
*|         32 kHz Slow External Crystal   Oscillator        |   MCME_SXOSC   |   Enabled   |X      |
*|           48 MHz Fast Internal RC   Oscillator           |        -       |   Enabled   |X      |
*|        8-40 MHz Fast External Crystal   Oscillator       |   MCME_FXOSC   |   Enabled   |X      |
*|                  Clock Generation Module                 |        -       |   Enabled   |X      |
*|                     Mode Entry Module                    |        -       |   Enabled   |X      |
*|          Frequency Modulated   Phase-Locked Loop         |    MCME_PLL    |      -      |X      |
*|                Power management controller               |        -       |   Enabled   |X      |
*|                       Flash memory                       |        -       |   Enabled   |X      |
*|                  Flash memory alternate                  |        -       |   Enabled   |X      |
*|              Programmable Interrupt Timer 2              |    MCME_PIT2   |      -      |X      |
*|                         FlexCAN 0                        |   MCME_FCAN0   |      -      |X      |
*|                         FlexCAN 1                        |   MCME_FCAN1   |      -      |X      |
*|                         FlexCAN 2                        |   MCME_FCAN2   |      -      |X      |
*|                         FlexCAN 3                        |   MCME_FCAN3   |      -      |X      |
*|                         FlexCAN 4                        |   MCME_FCAN4   |      -      |X      |
*|                         FlexCAN 5                        |   MCME_FCAN5   |      -      |X      |
*|                        Flexible IO                       |   MCME_FLEXIO  |      -      |X      |
*|                     Low Power UART 0                     |  MCME_LPUART0  |      -      |X      |
*|                     Low Power UART 1                     |  MCME_LPUART1  |      -      |X      |
*|                     Low Power UART 2                     |  MCME_LPUART2  |      -      |X      |
*|                     Low Power UART 3                     |  MCME_LPUART3  |      -      |X      |
*|                     Low Power UART 4                     |  MCME_LPUART4  |      -      |X      |
*|                     Low Power UART 5                     |  MCME_LPUART5  |      -      |X      |
*|                     Low Power UART 6                     |  MCME_LPUART6  |      -      |X      |
*|                     Low Power UART 7                     |  MCME_LPUART7  |      -      |X      |
*|                      Low Power I2C 0                     |   MCME_LPI2C0  |      -      |X      |
*|                      Low Power I2C 1                     |   MCME_LPI2C1  |      -      |X      |
*|                      Low Power SPI 0                     |   MCME_LPSPI0  |      -      |X      |
*|                      Low Power SPI 1                     |   MCME_LPSPI1  |      -      |X      |
*|                      Low Power SPI 2                     |   MCME_LPSPI2  |      -      |X      |
*|                      Low Power SPI 3                     |   MCME_LPSPI3  |      -      |X      |
*|               Synchronous Audio Interface 0              |    MCME_SAI0   |      -      |X      |
*|                      Low Power CMP 0                     |   MCME_LPCMP0  |   Enabled   |X      |
*|                      Low Power CMP 1                     |   MCME_LPCMP1  |   Enabled   |X      |
*|                TMU Temperature Sensor Unit               |    MCME_TMU    |      -      |X      |
*|                            CRC                           |    MCME_CRC    |      -      |X      |
*|                       FCCU (+FOSU)                       |        -       |   Enabled   |X      |
*|                  Memory Test and Repair                  |        -       |   Enabled   |X      |
*|                        HSE_B_MU0_B                       |        -       |   Enabled   |X      |
*|                        HSE_B_MU1_B                       |        -       |   Enabled   |X      |
*|               JDC (JTAG Data Communication)              |        -       |   Enabled   |X      |
*| Crossbar Integrity Checker   (TCM backdoor AHB_splitter) |        -       |   Enabled   |X      |
*|   Crossbar Integrity Checker   (eDMA & STAM AXBS-Lite)   |        -       |   Enabled   |X      |
*|           EDMA transfer control descriptor 12            |   MCME_TCD12   |      -      |-      |
*|           EDMA transfer control descriptor 13            |   MCME_TCD13   |      -      |-      |
*|           EDMA transfer control descriptor 14            |   MCME_TCD14   |      -      |-      |
*|           EDMA transfer control descriptor 15            |   MCME_TCD15   |      -      |-      |
*|           EDMA transfer control descriptor 16            |   MCME_TCD16   |      -      |-      |
*|           EDMA transfer control descriptor 17            |   MCME_TCD17   |      -      |-      |
*|           EDMA transfer control descriptor 18            |   MCME_TCD18   |      -      |-      |
*|           EDMA transfer control descriptor 19            |   MCME_TCD19   |      -      |-      |
*|           EDMA transfer control descriptor 20            |   MCME_TCD20   |      -      |-      |
*|           EDMA transfer control descriptor 21            |   MCME_TCD21   |      -      |-      |
*|           EDMA transfer control descriptor 22            |   MCME_TCD22   |      -      |-      |
*|           EDMA transfer control descriptor 23            |   MCME_TCD23   |      -      |-      |
*|           EDMA transfer control descriptor 24            |   MCME_TCD24   |      -      |-      |
*|           EDMA transfer control descriptor 25            |   MCME_TCD25   |      -      |-      |
*|           EDMA transfer control descriptor 26            |   MCME_TCD26   |      -      |-      |
*|           EDMA transfer control descriptor 27            |   MCME_TCD27   |      -      |-      |
*|           EDMA transfer control descriptor 28            |   MCME_TCD28   |      -      |-      |
*|           EDMA transfer control descriptor 29            |   MCME_TCD29   |      -      |-      |
*|           EDMA transfer control descriptor 30            |   MCME_TCD30   |      -      |-      |
*|           EDMA transfer control descriptor 31            |   MCME_TCD31   |      -      |-      |
*|                        Semaphores2                       |   MCME_SEMA42  |      -      |X      |
*|                     RAM controller 1                     |        -       |   Enabled   |X      |
*|                    Software Watchdog 1                   |    MCME_SWT1   |      -      |X      |
*|                   System Timer Module 1                  |    MCME_STM1   |      -      |X      |
*|                           ENET                           |    MCME_ENET   |      -      |X      |
*|                     Low Power UART 8                     |  MCME_LPUART8  |      -      |X      |
*|                     Low Power UART 9                     |  MCME_LPUART9  |      -      |X      |
*|                     Low Power UART 10                    |  MCME_LPUART10 |      -      |X      |
*|                     Low Power UART 11                    |  MCME_LPUART11 |      -      |X      |
*|                     Low Power UART 12                    |  MCME_LPUART12 |      -      |X      |
*|                     Low Power UART 13                    |  MCME_LPUART13 |      -      |X      |
*|                     Low Power UART 14                    |  MCME_LPUART14 |      -      |X      |
*|                     Low Power UART 15                    |  MCME_LPUART15 |      -      |X      |
*|                      Low Power SPI 4                     |   MCME_LPSPI4  |      -      |X      |
*|                      Low Power SPI 5                     |   MCME_LPSPI5  |      -      |X      |
*|                          QuadSPI                         |  MCME_QUADSPI  |      -      |-      |
*|               Synchronous Audio Interface 1              |    MCME_SAI1   |      -      |X      |
*|                      Low Power CMP 2                     |   MCME_LPCMP2  |   Enabled   |-      |
*|                        HSE_B_MU1_B                       |        -       |   Enabled   |X      |
*******************************************************************************/
/***************************************************************************//*!
 * @brief Enables clock to all on-chip peripherals.
 * @details Enables clock to all on-chip peripherals.
 * @showinitializer
 ******************************************************************************/
#define MCME_ALL_PERIPH_EN_CONFIG                                                                                          \
(tMCME){                                                                                                                   \
/* PRTN0_COFB1 */ SET(MCME_TRGMUX)|SET(MCME_BCTU)|SET(MCME_EMIOS0)|SET(MCME_EMIOS1)|SET(MCME_EMIOS2)|                      \
/* ..          */ SET(MCME_LCU0)|SET(MCME_LCU1)|SET(MCME_ADC0)|SET(MCME_ADC1)|SET(MCME_ADC2)|SET(MCME_PIT0)|               \
/* ..          */ SET(MCME_PIT1)|SET(MCME_MUA)|SET(MCME_MUB)|SET(MCME_I3C0),                                               \
/* PRTN1_COFB0 */ SET(MCME_EDMA)|SET(MCME_TCD0)|SET(MCME_TCD1)|SET(MCME_TCD2)|SET(MCME_TCD3)|SET(MCME_TCD4)|               \
/* ..          */ SET(MCME_TCD5)|SET(MCME_TCD6)|SET(MCME_TCD7)|SET(MCME_TCD8)|SET(MCME_TCD9)|SET(MCME_TCD10)|              \
/* ..          */ SET(MCME_TCD11)|SET(MCME_SDA)|SET(MCME_EIM)|SET(MCME_ERM)|SET(MCME_MSCM)|SET(MCME_SWT0)|                 \
/* ..          */ SET(MCME_STM0)|SET(MCME_INTM),                                                                           \
/* PRTN1_COFB1 */ SET(MCME_DMAMUX0)|SET(MCME_DMAMUX1)|SET(MCME_RTC)|SET(MCME_VWRAP)|SET(MCME_WKPU)|                        \
/* ..          */ SET(MCME_CMU05)|SET(MCME_TSPC)|SET(MCME_SXOSC)|SET(MCME_FXOSC)|SET(MCME_PLL)|SET(MCME_PIT2),             \
/* PRTN1_COFB2 */ SET(MCME_FCAN0)|SET(MCME_FCAN1)|SET(MCME_FCAN2)|SET(MCME_FCAN3)|SET(MCME_FCAN4)|                         \
/* ..          */ SET(MCME_FCAN5)|SET(MCME_FLEXIO)|SET(MCME_LPUART0)|SET(MCME_LPUART1)|SET(MCME_LPUART2)|                  \
/* ..          */ SET(MCME_LPUART3)|SET(MCME_LPUART4)|SET(MCME_LPUART5)|SET(MCME_LPUART6)|SET(MCME_LPUART7)|               \
/* ..          */ SET(MCME_LPI2C0)|SET(MCME_LPI2C1)|SET(MCME_LPSPI0)|SET(MCME_LPSPI1)|SET(MCME_LPSPI2)|                    \
/* ..          */ SET(MCME_LPSPI3)|SET(MCME_SAI0)|SET(MCME_LPCMP0)|SET(MCME_LPCMP1)|SET(MCME_TMU),                         \
/* PRTN1_COFB3 */ SET(MCME_CRC),                                                                                           \
/* PRTN2_COFB0 */ SET(MCME_TCD12)|SET(MCME_TCD13)|SET(MCME_TCD14)|SET(MCME_TCD15)|SET(MCME_TCD16)|SET(MCME_TCD17)|         \
/* ..          */ SET(MCME_TCD18)|SET(MCME_TCD19)|SET(MCME_TCD20)|SET(MCME_TCD21)|SET(MCME_TCD22)|SET(MCME_TCD23)|         \
/* ..          */ SET(MCME_TCD24)|SET(MCME_TCD25)|SET(MCME_TCD26)|SET(MCME_TCD27)|SET(MCME_TCD28)|SET(MCME_TCD29)|         \
/* ..          */ SET(MCME_TCD30)|SET(MCME_TCD31)|SET(MCME_SEMA42)|SET(MCME_SWT1)|SET(MCME_STM1),                          \
/* PRTN2_COFB1 */ SET(MCME_ENET)|SET(MCME_LPUART8)|SET(MCME_LPUART9)|SET(MCME_LPUART10)|SET(MCME_LPUART11)|                \
/* ..          */ SET(MCME_LPUART12)|SET(MCME_LPUART13)|SET(MCME_LPUART14)|SET(MCME_LPUART15)|SET(MCME_LPSPI4)|            \
/* ..          */ SET(MCME_LPSPI5)|SET(MCME_QUADSPI)|SET(MCME_SAI1)|SET(MCME_LPCMP2)|SET(MCME_TCMCORE0)|SET(MCME_TCMCORE1) \
}

/***************************************************************************//*!
 * @brief Disables clock to all on-chip peripherals, except reserved ones.
 * @details Disables clock to all on-chip peripherals, except reserved ones.
 * @showinitializer
 ******************************************************************************/
#define MCME_ALL_PERIPH_DI_CONFIG                                                                                          \
(tMCME){                                                                                                                   \
/* PRTN0_COFB1 */ CLR(MCME_TRGMUX)|CLR(MCME_BCTU)|CLR(MCME_EMIOS0)|CLR(MCME_EMIOS1)|CLR(MCME_EMIOS2)|                      \
/* ..          */ CLR(MCME_LCU0)|CLR(MCME_LCU1)|CLR(MCME_ADC0)|CLR(MCME_ADC1)|CLR(MCME_ADC2)|CLR(MCME_PIT0)|               \
/* ..          */ CLR(MCME_PIT1)|CLR(MCME_MUA)|CLR(MCME_MUB)|CLR(MCME_I3C0),                                               \
/* PRTN1_COFB0 */ CLR(MCME_EDMA)|CLR(MCME_TCD0)|CLR(MCME_TCD1)|CLR(MCME_TCD2)|CLR(MCME_TCD3)|CLR(MCME_TCD4)|               \
/* ..          */ CLR(MCME_TCD5)|CLR(MCME_TCD6)|CLR(MCME_TCD7)|CLR(MCME_TCD8)|CLR(MCME_TCD9)|CLR(MCME_TCD10)|              \
/* ..          */ CLR(MCME_TCD11)|CLR(MCME_SDA)|CLR(MCME_EIM)|CLR(MCME_ERM)|CLR(MCME_MSCM)|CLR(MCME_SWT0)|                 \
/* ..          */ CLR(MCME_STM0)|CLR(MCME_INTM),                                                                           \
/* PRTN1_COFB1 */ CLR(MCME_DMAMUX0)|CLR(MCME_DMAMUX1)|CLR(MCME_RTC)|CLR(MCME_VWRAP)|CLR(MCME_WKPU)|                        \
/* ..          */ CLR(MCME_CMU05)|CLR(MCME_TSPC)|CLR(MCME_SXOSC)|CLR(MCME_FXOSC)|CLR(MCME_PLL)|CLR(MCME_PIT2),             \
/* PRTN1_COFB2 */ CLR(MCME_FCAN0)|CLR(MCME_FCAN1)|CLR(MCME_FCAN2)|CLR(MCME_FCAN3)|CLR(MCME_FCAN4)|                         \
/* ..          */ CLR(MCME_FCAN5)|CLR(MCME_FLEXIO)|CLR(MCME_LPUART0)|CLR(MCME_LPUART1)|CLR(MCME_LPUART2)|                  \
/* ..          */ CLR(MCME_LPUART3)|CLR(MCME_LPUART4)|CLR(MCME_LPUART5)|CLR(MCME_LPUART6)|CLR(MCME_LPUART7)|               \
/* ..          */ CLR(MCME_LPI2C0)|CLR(MCME_LPI2C1)|CLR(MCME_LPSPI0)|CLR(MCME_LPSPI1)|CLR(MCME_LPSPI2)|                    \
/* ..          */ CLR(MCME_LPSPI3)|CLR(MCME_SAI0)|CLR(MCME_LPCMP0)|CLR(MCME_LPCMP1)|CLR(MCME_TMU),                         \
/* PRTN1_COFB3 */ CLR(MCME_CRC),                                                                                           \
/* PRTN2_COFB0 */ CLR(MCME_TCD12)|CLR(MCME_TCD13)|CLR(MCME_TCD14)|CLR(MCME_TCD15)|CLR(MCME_TCD16)|CLR(MCME_TCD17)|         \
/* ..          */ CLR(MCME_TCD18)|CLR(MCME_TCD19)|CLR(MCME_TCD20)|CLR(MCME_TCD21)|CLR(MCME_TCD22)|CLR(MCME_TCD23)|         \
/* ..          */ CLR(MCME_TCD24)|CLR(MCME_TCD25)|CLR(MCME_TCD26)|CLR(MCME_TCD27)|CLR(MCME_TCD28)|CLR(MCME_TCD29)|         \
/* ..          */ CLR(MCME_TCD30)|CLR(MCME_TCD31)|CLR(MCME_SEMA42)|CLR(MCME_SWT1)|CLR(MCME_STM1),                          \
/* PRTN2_COFB1 */ CLR(MCME_ENET)|CLR(MCME_LPUART8)|CLR(MCME_LPUART9)|CLR(MCME_LPUART10)|CLR(MCME_LPUART11)|                \
/* ..          */ CLR(MCME_LPUART12)|CLR(MCME_LPUART13)|CLR(MCME_LPUART14)|CLR(MCME_LPUART15)|CLR(MCME_LPSPI4)|            \
/* ..          */ CLR(MCME_LPSPI5)|CLR(MCME_QUADSPI)|CLR(MCME_SAI1)|CLR(MCME_LPCMP2)|CLR(MCME_TCMCORE0)|CLR(MCME_TCMCORE1) \
}

/***************************************************************************//*!
 * @brief Keeps clock enabled to on-chip peripherals enabled after device reset.
 * @details Keeps clock enabled to on-chip peripherals enabled after device reset.
 * @showinitializer
 ******************************************************************************/
#define MCME_DEF_PERIPH_EN_CONFIG                                                                                          \
(tMCME){                                                                                                                   \
/* PRTN0_COFB1 */ CLR(MCME_TRGMUX)|CLR(MCME_BCTU)|CLR(MCME_EMIOS0)|CLR(MCME_EMIOS1)|CLR(MCME_EMIOS2)|                      \
/* ..          */ CLR(MCME_LCU0)|CLR(MCME_LCU1)|CLR(MCME_ADC0)|CLR(MCME_ADC1)|CLR(MCME_ADC2)|SET(MCME_PIT0)|               \
/* ..          */ CLR(MCME_PIT1)|CLR(MCME_MUA)|CLR(MCME_MUB)|CLR(MCME_I3C0),                                               \
/* PRTN1_COFB0 */ CLR(MCME_EDMA)|CLR(MCME_TCD0)|CLR(MCME_TCD1)|CLR(MCME_TCD2)|CLR(MCME_TCD3)|CLR(MCME_TCD4)|               \
/* ..          */ CLR(MCME_TCD5)|CLR(MCME_TCD6)|CLR(MCME_TCD7)|CLR(MCME_TCD8)|CLR(MCME_TCD9)|CLR(MCME_TCD10)|              \
/* ..          */ CLR(MCME_TCD11)|SET(MCME_SDA)|CLR(MCME_EIM)|CLR(MCME_ERM)|CLR(MCME_MSCM)|SET(MCME_SWT0)|                 \
/* ..          */ CLR(MCME_STM0)|CLR(MCME_INTM),                                                                           \
/* PRTN1_COFB1 */ CLR(MCME_DMAMUX0)|CLR(MCME_DMAMUX1)|SET(MCME_RTC)|SET(MCME_VWRAP)|SET(MCME_WKPU)|                        \
/* ..          */ CLR(MCME_CMU05)|SET(MCME_TSPC)|SET(MCME_SXOSC)|SET(MCME_FXOSC)|CLR(MCME_PLL)|CLR(MCME_PIT2),             \
/* PRTN1_COFB2 */ CLR(MCME_FCAN0)|CLR(MCME_FCAN1)|CLR(MCME_FCAN2)|CLR(MCME_FCAN3)|CLR(MCME_FCAN4)|                         \
/* ..          */ CLR(MCME_FCAN5)|CLR(MCME_FLEXIO)|CLR(MCME_LPUART0)|CLR(MCME_LPUART1)|CLR(MCME_LPUART2)|                  \
/* ..          */ CLR(MCME_LPUART3)|CLR(MCME_LPUART4)|CLR(MCME_LPUART5)|CLR(MCME_LPUART6)|CLR(MCME_LPUART7)|               \
/* ..          */ CLR(MCME_LPI2C0)|CLR(MCME_LPI2C1)|CLR(MCME_LPSPI0)|CLR(MCME_LPSPI1)|CLR(MCME_LPSPI2)|                    \
/* ..          */ CLR(MCME_LPSPI3)|CLR(MCME_SAI0)|SET(MCME_LPCMP0)|SET(MCME_LPCMP1)|CLR(MCME_TMU),                         \
/* PRTN1_COFB3 */ CLR(MCME_CRC),                                                                                           \
/* PRTN2_COFB0 */ CLR(MCME_TCD12)|CLR(MCME_TCD13)|CLR(MCME_TCD14)|CLR(MCME_TCD15)|CLR(MCME_TCD16)|CLR(MCME_TCD17)|         \
/* ..          */ CLR(MCME_TCD18)|CLR(MCME_TCD19)|CLR(MCME_TCD20)|CLR(MCME_TCD21)|CLR(MCME_TCD22)|CLR(MCME_TCD23)|         \
/* ..          */ CLR(MCME_TCD24)|CLR(MCME_TCD25)|CLR(MCME_TCD26)|CLR(MCME_TCD27)|CLR(MCME_TCD28)|CLR(MCME_TCD29)|         \
/* ..          */ CLR(MCME_TCD30)|CLR(MCME_TCD31)|CLR(MCME_SEMA42)|CLR(MCME_SWT1)|CLR(MCME_STM1),                          \
/* PRTN2_COFB1 */ CLR(MCME_ENET)|CLR(MCME_LPUART8)|CLR(MCME_LPUART9)|CLR(MCME_LPUART10)|CLR(MCME_LPUART11)|                \
/* ..          */ CLR(MCME_LPUART12)|CLR(MCME_LPUART13)|CLR(MCME_LPUART14)|CLR(MCME_LPUART15)|CLR(MCME_LPSPI4)|            \
/* ..          */ CLR(MCME_LPSPI5)|CLR(MCME_QUADSPI)|CLR(MCME_SAI1)|SET(MCME_LPCMP2)|SET(MCME_TCMCORE0)|SET(MCME_TCMCORE1) \
}
/*! @} End of mcme_config                                                     */

/******************************************************************************
* MCME function and macro definitions
*
*//*! @addtogroup mcme_macro
* @{
*******************************************************************************/
/***************************************************************************//*!
 * @brief   Control state of on-chip peripherals.
 * @details This macro controls state of on-chip peripherals.
 * @param   cfg  One of @ref mcme_config.
 ******************************************************************************/
#define MCME_PeriphCtrl(cfg)                               \
do{                                                        \
  tMCME __t = cfg;                                         \
  MC_ME->PRTN0_COFB1_CLKEN = __t.PRTN0_COFB1 | 0x00000000; \
  MC_ME->PRTN1_COFB0_CLKEN = __t.PRTN1_COFB0 | 0x4E1F0007; \
  MC_ME->PRTN1_COFB1_CLKEN = __t.PRTN1_COFB1 | 0x1AD40BF8; \
  MC_ME->PRTN1_COFB2_CLKEN = __t.PRTN1_COFB2 | 0x00000000; \
  MC_ME->PRTN1_COFB3_CLKEN = __t.PRTN1_COFB3 | 0x00005FEE; \
  MC_ME->PRTN0_PCONF = MC_ME_PRTN0_PCONF_PCE_MASK;         \
  MC_ME->PRTN1_PCONF = MC_ME_PRTN1_PCONF_PCE_MASK;         \
  MC_ME->PRTN0_PUPD = MC_ME_PRTN0_PUPD_PCUD_MASK;          \
  MC_ME->PRTN1_PUPD = MC_ME_PRTN1_PUPD_PCUD_MASK;          \
  MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY( 0x5AF0);             \
  MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);             \
  while (MC_ME->PRTN0_PUPD & MC_ME_PRTN0_PUPD_PCUD_MASK){} \
  while (MC_ME->PRTN1_PUPD & MC_ME_PRTN1_PUPD_PCUD_MASK){} \
}while(0)

/***************************************************************************//*!
 * @brief   Transitions device into destructive or functional reset.
 * @details This macro transitions device into destructive or functional reset.
 * @param   type  @ref device_resets.
 ******************************************************************************/
#define MCME_EnterReset(type)                              \
do{                                                        \
  MC_ME->MODE_CONF = type;                                 \
  MC_ME->MODE_UPD = MC_ME_MODE_UPD_MODE_UPD_MASK;          \
  MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY( 0x5AF0);             \
  MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);             \
  while (MC_ME->MODE_UPD & MC_ME_MODE_UPD_MODE_UPD_MASK){} \
}while(0)

/***************************************************************************//*!
 * @brief   Transitions device to standby mode.
 * @details This macro transitions device to standby mode.
 * @param   core  One of @ref core_num.
 * @warning Make sure at least one working wake-up source is enabled prior
 * entering into standby mode otherwise your device will be locked with no way
 * for recovery.
 * @see     @ref MSCM_CoreNum
 ******************************************************************************/
#define MCME_EnterStby(core)                                      \
do{                                                               \
  MC_ME->MAIN_COREID = MC_ME_MAIN_COREID_CIDX(coreid_cidx[core])| \
                       MC_ME_MAIN_COREID_PIDX(coreid_pidx[core]); \
  MC_ME->MODE_CONF = MC_ME_MODE_CONF_STANDBY_MASK;                \
  MC_ME->MODE_UPD = MC_ME_MODE_UPD_MODE_UPD_MASK;                 \
  MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY( 0x5AF0);                    \
  MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);                    \
  __asm volatile ("wfi");                                         \
}while(0)

/***************************************************************************//*!
 * @brief   Returns true (non-zero) if device exits from standby mode.
 * @details This macro returns true (non-zero) if device exits from standby mode.
 * The false is returned if device wakes up from any reset condition.
 ****************************************************************************/
#define MCME_ExitFromStby() MC_ME->MODE_STAT

/***************************************************************************//*!
 * @brief   Returns true (non-zero) if device exits from any reset mode.
 * @details This macro returns true (non-zero) if device exits from any reset mode.
 * The false is returned if device exits from standby mode.
 ******************************************************************************/
#define MCME_ExitFromReset() !MC_ME->MODE_STAT

/***************************************************************************//*!
 * @brief   Starts core from given (default) boot address.
 * @details This function starts core from given (default) boot address.
 * @param   mask One of @ref core_list.
 * @param   vtor int32_t boot address aligned to four bytes
 ******************************************************************************/
#define MCME_CoreStart(mask, vtor)                                        \
do{                                                                       \
  if      ((mask) & MCME_CORE0) {                                         \
    MC_ME->PRTN0_CORE0_ADDR = (uint32_t)(vtor);                           \
    MC_ME->PRTN0_CORE0_PCONF = MC_ME_PRTN0_CORE0_PCONF_CCE_MASK;          \
    MC_ME->PRTN0_CORE0_PUPD = MC_ME_PRTN0_CORE0_PUPD_CCUPD_MASK;          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY( 0x5AF0);                          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);                          \
    while (MC_ME->PRTN0_CORE0_PUPD & MC_ME_PRTN0_CORE0_PUPD_CCUPD_MASK){} \
  }                                                                       \
  else if ((mask) & MCME_CORE1) {                                         \
    MC_ME->PRTN0_CORE1_ADDR = (uint32_t)(vtor);                           \
    MC_ME->PRTN0_CORE1_PCONF = MC_ME_PRTN0_CORE1_PCONF_CCE_MASK;          \
    MC_ME->PRTN0_CORE1_PUPD = MC_ME_PRTN0_CORE1_PUPD_CCUPD_MASK;          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY( 0x5AF0);                          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);                          \
    while (MC_ME->PRTN0_CORE1_PUPD & MC_ME_PRTN0_CORE1_PUPD_CCUPD_MASK){} \
  }                                                                       \
}while(0)

/***************************************************************************//*!
 * @brief   Stop core(s).
 * @details This function stops core operation from given (default) boot address.
 * @param   mask Mask of @ref core_list.
 * default address)
 ******************************************************************************/
#define MCME_CoreStop(mask)                                               \
do{                                                                       \
  if ((mask) & MCME_CORE0) {                                              \
    MC_ME->PRTN0_CORE0_PCONF = 0;                                         \
    MC_ME->PRTN0_CORE0_PUPD = MC_ME_PRTN0_CORE0_PUPD_CCUPD_MASK;          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY( 0x5AF0);                          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);                          \
    while (MC_ME->PRTN0_CORE0_PUPD & MC_ME_PRTN0_CORE0_PUPD_CCUPD_MASK){} \
  }                                                                       \
  if ((mask) & MCME_CORE1) {                                              \
    MC_ME->PRTN0_CORE1_PCONF = 0;                                         \
    MC_ME->PRTN0_CORE1_PUPD = MC_ME_PRTN0_CORE1_PUPD_CCUPD_MASK;          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY( 0x5AF0);                          \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);                          \
    while (MC_ME->PRTN0_CORE1_PUPD & MC_ME_PRTN0_CORE1_PUPD_CCUPD_MASK){} \
  }                                                                       \
}while(0)
/*! @} End of mcme_macro                                                      */

#endif /* __MCME_H */
