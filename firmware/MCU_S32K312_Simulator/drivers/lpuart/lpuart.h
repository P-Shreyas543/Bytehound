/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      lpuart.h
 * @brief     Low Power Universal Asynchronous Receiver/Transmitter (LPUART)
 *            driver header file.
 */
#ifndef __LPUART_H
#define __LPUART_H

/******************************************************************************
* LPUART modules
*//*! @addtogroup lpuart_modules
* @{
* @details LPUART modules support:
* |Module  |S32K312|
* |:------:|:-----:|
* |LPUART0 |X      |
* |LPUART1 |X      |
* |LPUART2 |X      |
* |LPUART3 |X      |
* |LPUART4 |X      |
* |LPUART5 |X      |
* |LPUART6 |X      |
* |LPUART7 |X      |
* |LPUART8 |-      |
* |LPUART9 |-      |
* |LPUART10|-      |
* |LPUART11|-      |
* |LPUART12|-      |
* |LPUART13|-      |
* |LPUART14|-      |
* |LPUART15|-      |
*******************************************************************************/
#if defined(LPUART_0_BASE)
  #define LPUART0  ((LPUART_Type *)LPUART_0_BASE) ///< LPUART0 module
#endif
#if defined(LPUART_1_BASE)
  #define LPUART1  ((LPUART_Type *)LPUART_1_BASE) ///< LPUART1 module
#endif
#if defined(LPUART_2_BASE)
  #define LPUART2  ((LPUART_Type *)LPUART_2_BASE) ///< LPUART2 module
#endif
#if defined(LPUART_3_BASE)
  #define LPUART3  ((LPUART_Type *)LPUART_3_BASE) ///< LPUART3 module
#endif
#if defined(LPUART_4_BASE)
  #define LPUART4  ((LPUART_Type *)LPUART_4_BASE) ///< LPUART4 module
#endif
#if defined(LPUART_5_BASE)
  #define LPUART5  ((LPUART_Type *)LPUART_5_BASE) ///< LPUART5 module
#endif
#if defined(LPUART_6_BASE)
  #define LPUART6  ((LPUART_Type *)LPUART_6_BASE) ///< LPUART6 module
#endif
#if defined(LPUART_7_BASE)
  #define LPUART7  ((LPUART_Type *)LPUART_7_BASE) ///< LPUART7 module
#endif
#if defined(LPUART_8_BASE)
  #define LPUART8  ((LPUART_Type *)LPUART_8_BASE) ///< LPUART8 module
#endif
#if defined(LPUART_9_BASE)
  #define LPUART9  ((LPUART_Type *)LPUART_9_BASE) ///< LPUART9 module
#endif
#if defined(LPUART_10_BASE)
  #define LPUART10  ((LPUART_Type *)LPUART_10_BASE) ///< LPUART10 module
#endif
#if defined(LPUART_11_BASE)
  #define LPUART11  ((LPUART_Type *)LPUART_11_BASE) ///< LPUART11 module
#endif
#if defined(LPUART_12_BASE)
  #define LPUART12  ((LPUART_Type *)LPUART_12_BASE) ///< LPUART12 module
#endif
#if defined(LPUART_13_BASE)
  #define LPUART13  ((LPUART_Type *)LPUART_13_BASE) ///< LPUART13 module
#endif
#if defined(LPUART_14_BASE)
  #define LPUART14  ((LPUART_Type *)LPUART_14_BASE) ///< LPUART14 module
#endif
#if defined(LPUART_15_BASE)
  #define LPUART15  ((LPUART_Type *)LPUART_15_BASE) ///< LPUART15 module
#endif
/*! @} End of lpuart_modules                                                  */

/******************************************************************************
 * Configuration structure definitions                                        *
 ******************************************************************************/
typedef struct { uint32_t PINCFG, BAUD, STAT, CTRL, MODIR; } tLPUART;

#define LPUART_OSR_FIXED                      (uint8_t)15u
#define LPUART_CALC_SBR_OSR(brate,clk,osr)    (uint16_t)((float)clk/(((float)osr+1.0)*(float)brate))
#define LPUART_CALC_SBR(brate,clk)            LPUART_CALC_SBR_OSR(brate,clk,LPUART_OSR_FIXED)

/******************************************************************************
* LPUART default configurations used by LPUART_Init()
*
*//*! @addtogroup lpuart_config
* @{
*******************************************************************************/
/***************************************************************************//*!
 * @brief   LPUART - Polling Mode.
 * @details Configures LPUART for the simplest polling mode.
 * @param   brate     Baud rate.
 * @param   clk       Module clock in Hz.
 * @showinitializer
 ******************************************************************************/
#define LPUART_POLLMODE_CONFIG(brate, clk)                                                          \
(tLPUART) {                                                                                         \
/* PINCFG */ SET(LPUART_PINCFG_TRGSEL(0x0)),                                                        \
/* BAUD   */ SET(LPUART_BAUD_SBR(LPUART_CALC_SBR(brate,clk)))|                                      \
/* ....   */ SET(LPUART_BAUD_OSR(LPUART_OSR_FIXED))|                                                \
/* ....   */ CLR(LPUART_BAUD_MAEN1_MASK)|CLR(LPUART_BAUD_MAEN2_MASK)|CLR(LPUART_BAUD_M10_MASK)|     \
/* ....   */ CLR(LPUART_BAUD_TDMAE_MASK)|CLR(LPUART_BAUD_RDMAE_MASK)|SET(LPUART_BAUD_MATCFG(0x0))|  \
/* ....   */ CLR(LPUART_BAUD_BOTHEDGE_MASK)|CLR(LPUART_BAUD_RESYNCDIS_MASK)|                        \
/* ....   */ CLR(LPUART_BAUD_LBKDIE_MASK)|CLR(LPUART_BAUD_RXEDGIE_MASK)|CLR(LPUART_BAUD_SBNS_MASK), \
/* STAT   */ CLR(LPUART_STAT_MSBF_MASK)|CLR(LPUART_STAT_RXINV_MASK)|CLR(LPUART_STAT_RWUID_MASK)|    \
/* ....   */ CLR(LPUART_STAT_BRK13_MASK)|CLR(LPUART_STAT_LBKDE_MASK)|                               \
/* ....   */ CLR(LPUART_STAT_AME_MASK) |CLR(LPUART_STAT_LBKFE_MASK),                                \
/* CTRL   */ SET(LPUART_CTRL_RE_MASK)|SET(LPUART_CTRL_TE_MASK)|                                     \
/* ....   */ CLR(LPUART_CTRL_PT_MASK)|CLR(LPUART_CTRL_PE_MASK)|CLR(LPUART_CTRL_PEIE_MASK)|          \
/* ....   */ CLR(LPUART_CTRL_M_MASK) |CLR(LPUART_CTRL_M7_MASK)|SET(LPUART_CTRL_IDLECFG(0x0)) |      \
/* ....   */ CLR(LPUART_CTRL_MA1IE_MASK)|CLR(LPUART_CTRL_MA2IE_MASK)|CLR(LPUART_CTRL_ILIE_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RIE_MASK)|CLR(LPUART_CTRL_TCIE_MASK)|CLR(LPUART_CTRL_TIE_MASK)|        \
/* ....   */ CLR(LPUART_CTRL_FEIE_MASK)|CLR(LPUART_CTRL_NEIE_MASK)|CLR(LPUART_CTRL_ORIE_MASK) |     \
/* ....   */ CLR(LPUART_CTRL_TXINV_MASK)|CLR(LPUART_CTRL_TXDIR_MASK)|CLR(LPUART_CTRL_RSRC_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RWU_MASK)|CLR(LPUART_CTRL_SBK_MASK)|CLR(LPUART_CTRL_ILT_MASK)|         \
/* ....   */ CLR(LPUART_CTRL_WAKE_MASK)|CLR(LPUART_CTRL_DOZEEN_MASK)|CLR(LPUART_CTRL_LOOPS_MASK)|   \
/* ....   */ CLR(LPUART_CTRL_R8T9_MASK)|CLR(LPUART_CTRL_R9T8_MASK),                                 \
/* MODIR  */ SET(LPUART_MODIR_RTSWATER(0x0))|SET(LPUART_MODIR_TNP(0x0))|                            \
/* .....  */ CLR(LPUART_MODIR_IREN_MASK)|CLR(LPUART_MODIR_TXCTSSRC_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXCTSC_MASK)|CLR(LPUART_MODIR_RXRTSE_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXRTSPOL_MASK)|CLR(LPUART_MODIR_TXRTSE_MASK)|                         \
/* .....  */ CLR(LPUART_MODIR_TXCTSE_MASK)                                                          \
}
/***************************************************************************//*!
 * @brief   LPUART - Polling Mode, Invert transmit data.
 * @details Configures LPUART for the simplest polling mode, transmit data is inverted.
 * @param   brate     Baud rate.
 * @param   clk       Module clock in Hz.
 * @showinitializer
 ******************************************************************************/
#define LPUART_POLLMODE_TXINV_CONFIG(brate, clk)                                                    \
(tLPUART) {                                                                                         \
/* PINCFG */ SET(LPUART_PINCFG_TRGSEL(0x0)),                                                        \
/* BAUD   */ SET(LPUART_BAUD_SBR(LPUART_CALC_SBR(brate,clk)))|                                      \
/* ....   */ SET(LPUART_BAUD_OSR(LPUART_OSR_FIXED))|                                                \
/* ....   */ CLR(LPUART_BAUD_MAEN1_MASK)|CLR(LPUART_BAUD_MAEN2_MASK)|CLR(LPUART_BAUD_M10_MASK)|     \
/* ....   */ CLR(LPUART_BAUD_TDMAE_MASK)|CLR(LPUART_BAUD_RDMAE_MASK)|SET(LPUART_BAUD_MATCFG(0x0))|  \
/* ....   */ CLR(LPUART_BAUD_BOTHEDGE_MASK)|CLR(LPUART_BAUD_RESYNCDIS_MASK)|                        \
/* ....   */ CLR(LPUART_BAUD_LBKDIE_MASK)|CLR(LPUART_BAUD_RXEDGIE_MASK)|CLR(LPUART_BAUD_SBNS_MASK), \
/* STAT   */ CLR(LPUART_STAT_MSBF_MASK)|CLR(LPUART_STAT_RXINV_MASK)|CLR(LPUART_STAT_RWUID_MASK)|    \
/* ....   */ CLR(LPUART_STAT_BRK13_MASK)|CLR(LPUART_STAT_LBKDE_MASK)|                               \
/* ....   */ CLR(LPUART_STAT_AME_MASK) |CLR(LPUART_STAT_LBKFE_MASK),                                \
/* CTRL   */ SET(LPUART_CTRL_RE_MASK)|SET(LPUART_CTRL_TE_MASK)|                                     \
/* ....   */ CLR(LPUART_CTRL_PT_MASK)|CLR(LPUART_CTRL_PE_MASK)|CLR(LPUART_CTRL_PEIE_MASK)|          \
/* ....   */ CLR(LPUART_CTRL_M_MASK) |CLR(LPUART_CTRL_M7_MASK)|SET(LPUART_CTRL_IDLECFG(0x0)) |      \
/* ....   */ CLR(LPUART_CTRL_MA1IE_MASK)|CLR(LPUART_CTRL_MA2IE_MASK)|CLR(LPUART_CTRL_ILIE_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RIE_MASK)|CLR(LPUART_CTRL_TCIE_MASK)|CLR(LPUART_CTRL_TIE_MASK)|        \
/* ....   */ CLR(LPUART_CTRL_FEIE_MASK)|CLR(LPUART_CTRL_NEIE_MASK)|CLR(LPUART_CTRL_ORIE_MASK) |     \
/* ....   */ SET(LPUART_CTRL_TXINV_MASK)|CLR(LPUART_CTRL_TXDIR_MASK)|CLR(LPUART_CTRL_RSRC_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RWU_MASK)|CLR(LPUART_CTRL_SBK_MASK)|CLR(LPUART_CTRL_ILT_MASK)|         \
/* ....   */ CLR(LPUART_CTRL_WAKE_MASK)|CLR(LPUART_CTRL_DOZEEN_MASK)|CLR(LPUART_CTRL_LOOPS_MASK)|   \
/* ....   */ CLR(LPUART_CTRL_R8T9_MASK)|CLR(LPUART_CTRL_R9T8_MASK),                                 \
/* MODIR  */ SET(LPUART_MODIR_RTSWATER(0x0))|SET(LPUART_MODIR_TNP(0x0))|                            \
/* .....  */ CLR(LPUART_MODIR_IREN_MASK)|CLR(LPUART_MODIR_TXCTSSRC_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXCTSC_MASK)|CLR(LPUART_MODIR_RXRTSE_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXRTSPOL_MASK)|CLR(LPUART_MODIR_TXRTSE_MASK)|                         \
/* .....  */ CLR(LPUART_MODIR_TXCTSE_MASK)                                                          \
}
/***************************************************************************//*!
 * @brief   LPUART - Interrupt Mode.
 * @details Configures LPUART to operate in interrupt mode.
 * @param   brate     Baud rate.
 * @param   clk       Module clock in Hz.
 * @showinitializer
 ******************************************************************************/
#define LPUART_INTRMODE_CONFIG(brate, clk)                                                          \
(tLPUART) {                                                                                         \
/* PINCFG */ SET(LPUART_PINCFG_TRGSEL(0x0)),                                                        \
/* BAUD   */ SET(LPUART_BAUD_SBR(LPUART_CALC_SBR(brate,clk)))|                                      \
/* ....   */ SET(LPUART_BAUD_OSR(LPUART_OSR_FIXED))|                                                \
/* ....   */ CLR(LPUART_BAUD_MAEN1_MASK)|CLR(LPUART_BAUD_MAEN2_MASK)|CLR(LPUART_BAUD_M10_MASK)|     \
/* ....   */ CLR(LPUART_BAUD_TDMAE_MASK)|CLR(LPUART_BAUD_RDMAE_MASK)|SET(LPUART_BAUD_MATCFG(0x0))|  \
/* ....   */ CLR(LPUART_BAUD_BOTHEDGE_MASK)|CLR(LPUART_BAUD_RESYNCDIS_MASK)|                        \
/* ....   */ CLR(LPUART_BAUD_LBKDIE_MASK)|CLR(LPUART_BAUD_RXEDGIE_MASK)|CLR(LPUART_BAUD_SBNS_MASK), \
/* STAT   */ CLR(LPUART_STAT_MSBF_MASK)|CLR(LPUART_STAT_RXINV_MASK)|CLR(LPUART_STAT_RWUID_MASK)|    \
/* ....   */ CLR(LPUART_STAT_BRK13_MASK)|CLR(LPUART_STAT_LBKDE_MASK)|                               \
/* ....   */ CLR(LPUART_STAT_AME_MASK) |CLR(LPUART_STAT_LBKFE_MASK),                                \
/* CTRL   */ SET(LPUART_CTRL_RE_MASK)|SET(LPUART_CTRL_TE_MASK)|                                     \
/* ....   */ CLR(LPUART_CTRL_PT_MASK)|CLR(LPUART_CTRL_PE_MASK)|CLR(LPUART_CTRL_PEIE_MASK)|          \
/* ....   */ CLR(LPUART_CTRL_M_MASK) |CLR(LPUART_CTRL_M7_MASK)|SET(LPUART_CTRL_IDLECFG(0x0)) |      \
/* ....   */ CLR(LPUART_CTRL_MA1IE_MASK)|CLR(LPUART_CTRL_MA2IE_MASK)|CLR(LPUART_CTRL_ILIE_MASK)|    \
/* ....   */ SET(LPUART_CTRL_RIE_MASK)|CLR(LPUART_CTRL_TCIE_MASK)|CLR(LPUART_CTRL_TIE_MASK)|        \
/* ....   */ CLR(LPUART_CTRL_FEIE_MASK)|CLR(LPUART_CTRL_NEIE_MASK)|CLR(LPUART_CTRL_ORIE_MASK) |     \
/* ....   */ CLR(LPUART_CTRL_TXINV_MASK)|CLR(LPUART_CTRL_TXDIR_MASK)|CLR(LPUART_CTRL_RSRC_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RWU_MASK)|CLR(LPUART_CTRL_SBK_MASK)|CLR(LPUART_CTRL_ILT_MASK)|         \
/* ....   */ CLR(LPUART_CTRL_WAKE_MASK)|CLR(LPUART_CTRL_DOZEEN_MASK)|CLR(LPUART_CTRL_LOOPS_MASK)|   \
/* ....   */ CLR(LPUART_CTRL_R8T9_MASK)|CLR(LPUART_CTRL_R9T8_MASK),                                 \
/* MODIR  */ SET(LPUART_MODIR_RTSWATER(0x0))|SET(LPUART_MODIR_TNP(0x0))|                            \
/* .....  */ CLR(LPUART_MODIR_IREN_MASK)|CLR(LPUART_MODIR_TXCTSSRC_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXCTSC_MASK)|CLR(LPUART_MODIR_RXRTSE_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXRTSPOL_MASK)|CLR(LPUART_MODIR_TXRTSE_MASK)|                         \
/* .....  */ CLR(LPUART_MODIR_TXCTSE_MASK)                                                          \
}
/***************************************************************************//*!
 * @brief   LPUART - Interrupt Mode, Invert Transmit data.
 * @details Configures LPUART to operate in interrupt mode. Receive data is not
 *          inverted. Transmit data is inverted.
 * @param   brate     Baud rate.
 * @param   clk       Module clock in Hz.
 * @showinitializer
 ******************************************************************************/
#define LPUART_INTRMODE_TXINV_CONFIG(brate, clk)                                                    \
(tLPUART) {                                                                                         \
/* PINCFG */ SET(LPUART_PINCFG_TRGSEL(0x0)),                                                        \
/* BAUD   */ SET(LPUART_BAUD_SBR(LPUART_CALC_SBR(brate,clk)))|                                      \
/* ....   */ SET(LPUART_BAUD_OSR(LPUART_OSR_FIXED))|                                                \
/* ....   */ CLR(LPUART_BAUD_MAEN1_MASK)|CLR(LPUART_BAUD_MAEN2_MASK)|CLR(LPUART_BAUD_M10_MASK)|     \
/* ....   */ CLR(LPUART_BAUD_TDMAE_MASK)|CLR(LPUART_BAUD_RDMAE_MASK)|SET(LPUART_BAUD_MATCFG(0x0))|  \
/* ....   */ CLR(LPUART_BAUD_BOTHEDGE_MASK)|CLR(LPUART_BAUD_RESYNCDIS_MASK)|                        \
/* ....   */ CLR(LPUART_BAUD_LBKDIE_MASK)|CLR(LPUART_BAUD_RXEDGIE_MASK)|CLR(LPUART_BAUD_SBNS_MASK), \
/* STAT   */ CLR(LPUART_STAT_MSBF_MASK)|CLR(LPUART_STAT_RXINV_MASK)|CLR(LPUART_STAT_RWUID_MASK)|    \
/* ....   */ CLR(LPUART_STAT_BRK13_MASK)|CLR(LPUART_STAT_LBKDE_MASK)|                               \
/* ....   */ CLR(LPUART_STAT_AME_MASK) |CLR(LPUART_STAT_LBKFE_MASK),                                \
/* CTRL   */ SET(LPUART_CTRL_RE_MASK)|SET(LPUART_CTRL_TE_MASK)|                                     \
/* ....   */ CLR(LPUART_CTRL_PT_MASK)|CLR(LPUART_CTRL_PE_MASK)|CLR(LPUART_CTRL_PEIE_MASK)|          \
/* ....   */ CLR(LPUART_CTRL_M_MASK) |CLR(LPUART_CTRL_M7_MASK)|SET(LPUART_CTRL_IDLECFG(0x0)) |      \
/* ....   */ CLR(LPUART_CTRL_MA1IE_MASK)|CLR(LPUART_CTRL_MA2IE_MASK)|CLR(LPUART_CTRL_ILIE_MASK)|    \
/* ....   */ SET(LPUART_CTRL_RIE_MASK)|CLR(LPUART_CTRL_TCIE_MASK)|CLR(LPUART_CTRL_TIE_MASK)|        \
/* ....   */ CLR(LPUART_CTRL_FEIE_MASK)|CLR(LPUART_CTRL_NEIE_MASK)|CLR(LPUART_CTRL_ORIE_MASK) |     \
/* ....   */ SET(LPUART_CTRL_TXINV_MASK)|CLR(LPUART_CTRL_TXDIR_MASK)|CLR(LPUART_CTRL_RSRC_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RWU_MASK)|CLR(LPUART_CTRL_SBK_MASK)|CLR(LPUART_CTRL_ILT_MASK)|         \
/* ....   */ CLR(LPUART_CTRL_WAKE_MASK)|CLR(LPUART_CTRL_DOZEEN_MASK)|CLR(LPUART_CTRL_LOOPS_MASK)|   \
/* ....   */ CLR(LPUART_CTRL_R8T9_MASK)|CLR(LPUART_CTRL_R9T8_MASK),                                 \
/* MODIR  */ SET(LPUART_MODIR_RTSWATER(0x0))|SET(LPUART_MODIR_TNP(0x0))|                            \
/* .....  */ CLR(LPUART_MODIR_IREN_MASK)|CLR(LPUART_MODIR_TXCTSSRC_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXCTSC_MASK)|CLR(LPUART_MODIR_RXRTSE_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXRTSPOL_MASK)|CLR(LPUART_MODIR_TXRTSE_MASK)|                         \
/* .....  */ CLR(LPUART_MODIR_TXCTSE_MASK)                                                          \
}
/***************************************************************************//*!
 * @brief   LPUART - Receive DMA Mode.
 * @details Configures LPUART to operate in receive DMA mode. Receive data
 *          register full flag will cause DMA request.
 * @param   brate     Baud rate.
 * @param   clk       Module clock in Hz.
 * @showinitializer
 ******************************************************************************/
#define LPUART_RDRF_DMAMODE_CONFIG(brate, clk)                                                      \
(tLPUART) {                                                                                         \
/* PINCFG */ SET(LPUART_PINCFG_TRGSEL(0x0)),                                                        \
/* BAUD   */ SET(LPUART_BAUD_SBR(LPUART_CALC_SBR(brate,clk)))|                                      \
/* ....   */ SET(LPUART_BAUD_OSR(LPUART_OSR_FIXED))|                                                \
/* ....   */ CLR(LPUART_BAUD_MAEN1_MASK)|CLR(LPUART_BAUD_MAEN2_MASK)|CLR(LPUART_BAUD_M10_MASK)|     \
/* ....   */ CLR(LPUART_BAUD_TDMAE_MASK)|SET(LPUART_BAUD_RDMAE_MASK)|SET(LPUART_BAUD_MATCFG(0x0))|  \
/* ....   */ CLR(LPUART_BAUD_BOTHEDGE_MASK)|CLR(LPUART_BAUD_RESYNCDIS_MASK)|                        \
/* ....   */ CLR(LPUART_BAUD_LBKDIE_MASK)|CLR(LPUART_BAUD_RXEDGIE_MASK)|CLR(LPUART_BAUD_SBNS_MASK), \
/* STAT   */ CLR(LPUART_STAT_MSBF_MASK)|CLR(LPUART_STAT_RXINV_MASK)|CLR(LPUART_STAT_RWUID_MASK)|    \
/* ....   */ CLR(LPUART_STAT_BRK13_MASK)|CLR(LPUART_STAT_LBKDE_MASK)|                               \
/* ....   */ CLR(LPUART_STAT_AME_MASK) |CLR(LPUART_STAT_LBKFE_MASK),                                \
/* CTRL   */ SET(LPUART_CTRL_RE_MASK)|SET(LPUART_CTRL_TE_MASK)|                                     \
/* ....   */ CLR(LPUART_CTRL_PT_MASK)|CLR(LPUART_CTRL_PE_MASK)|CLR(LPUART_CTRL_PEIE_MASK)|          \
/* ....   */ CLR(LPUART_CTRL_M_MASK) |CLR(LPUART_CTRL_M7_MASK)|SET(LPUART_CTRL_IDLECFG(0x0)) |      \
/* ....   */ CLR(LPUART_CTRL_MA1IE_MASK)|CLR(LPUART_CTRL_MA2IE_MASK)|CLR(LPUART_CTRL_ILIE_MASK)|    \
/* ....   */ SET(LPUART_CTRL_RIE_MASK)|CLR(LPUART_CTRL_TCIE_MASK)|CLR(LPUART_CTRL_TIE_MASK)|        \
/* ....   */ CLR(LPUART_CTRL_FEIE_MASK)|CLR(LPUART_CTRL_NEIE_MASK)|CLR(LPUART_CTRL_ORIE_MASK) |     \
/* ....   */ CLR(LPUART_CTRL_TXINV_MASK)|CLR(LPUART_CTRL_TXDIR_MASK)|CLR(LPUART_CTRL_RSRC_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RWU_MASK)|CLR(LPUART_CTRL_SBK_MASK)|CLR(LPUART_CTRL_ILT_MASK)|         \
/* ....   */ CLR(LPUART_CTRL_WAKE_MASK)|CLR(LPUART_CTRL_DOZEEN_MASK)|CLR(LPUART_CTRL_LOOPS_MASK)|   \
/* ....   */ CLR(LPUART_CTRL_R8T9_MASK)|CLR(LPUART_CTRL_R9T8_MASK),                                 \
/* MODIR  */ SET(LPUART_MODIR_RTSWATER(0x0))|SET(LPUART_MODIR_TNP(0x0))|                            \
/* .....  */ CLR(LPUART_MODIR_IREN_MASK)|CLR(LPUART_MODIR_TXCTSSRC_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXCTSC_MASK)|CLR(LPUART_MODIR_RXRTSE_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXRTSPOL_MASK)|CLR(LPUART_MODIR_TXRTSE_MASK)|                         \
/* .....  */ CLR(LPUART_MODIR_TXCTSE_MASK)                                                          \
}
/***************************************************************************//*!
 * @brief   LPUART - Transmit DMA Mode.
 * @details Configures LPUART to operate in transmit DMA mode. Transmit data
 *          register empty flag will cause DMA request.
 * @param   brate     Baud rate.
 * @param   clk       Module clock in Hz.
 * @showinitializer
 ******************************************************************************/
#define LPUART_TDRE_DMAMODE_CONFIG(brate, clk)                                                      \
(tLPUART) {                                                                                         \
/* PINCFG */ SET(LPUART_PINCFG_TRGSEL(0x0)),                                                        \
/* BAUD   */ SET(LPUART_BAUD_SBR(LPUART_CALC_SBR(brate,clk)))|                                      \
/* ....   */ SET(LPUART_BAUD_OSR(LPUART_OSR_FIXED))|                                                \
/* ....   */ CLR(LPUART_BAUD_MAEN1_MASK)|CLR(LPUART_BAUD_MAEN2_MASK)|CLR(LPUART_BAUD_M10_MASK)|     \
/* ....   */ SET(LPUART_BAUD_TDMAE_MASK)|CLR(LPUART_BAUD_RDMAE_MASK)|SET(LPUART_BAUD_MATCFG(0x0))|  \
/* ....   */ CLR(LPUART_BAUD_BOTHEDGE_MASK)|CLR(LPUART_BAUD_RESYNCDIS_MASK)|                        \
/* ....   */ CLR(LPUART_BAUD_LBKDIE_MASK)|CLR(LPUART_BAUD_RXEDGIE_MASK)|CLR(LPUART_BAUD_SBNS_MASK), \
/* STAT   */ CLR(LPUART_STAT_MSBF_MASK)|CLR(LPUART_STAT_RXINV_MASK)|CLR(LPUART_STAT_RWUID_MASK)|    \
/* ....   */ CLR(LPUART_STAT_BRK13_MASK)|CLR(LPUART_STAT_LBKDE_MASK)|                               \
/* ....   */ CLR(LPUART_STAT_AME_MASK) |CLR(LPUART_STAT_LBKFE_MASK),                                \
/* CTRL   */ SET(LPUART_CTRL_RE_MASK)|SET(LPUART_CTRL_TE_MASK)|                                     \
/* ....   */ CLR(LPUART_CTRL_PT_MASK)|CLR(LPUART_CTRL_PE_MASK)|CLR(LPUART_CTRL_PEIE_MASK)|          \
/* ....   */ CLR(LPUART_CTRL_M_MASK) |CLR(LPUART_CTRL_M7_MASK)|SET(LPUART_CTRL_IDLECFG(0x0)) |      \
/* ....   */ CLR(LPUART_CTRL_MA1IE_MASK)|CLR(LPUART_CTRL_MA2IE_MASK)|CLR(LPUART_CTRL_ILIE_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RIE_MASK)|CLR(LPUART_CTRL_TCIE_MASK)|SET(LPUART_CTRL_TIE_MASK)|        \
/* ....   */ CLR(LPUART_CTRL_FEIE_MASK)|CLR(LPUART_CTRL_NEIE_MASK)|CLR(LPUART_CTRL_ORIE_MASK) |     \
/* ....   */ CLR(LPUART_CTRL_TXINV_MASK)|CLR(LPUART_CTRL_TXDIR_MASK)|CLR(LPUART_CTRL_RSRC_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RWU_MASK)|CLR(LPUART_CTRL_SBK_MASK)|CLR(LPUART_CTRL_ILT_MASK)|         \
/* ....   */ CLR(LPUART_CTRL_WAKE_MASK)|CLR(LPUART_CTRL_DOZEEN_MASK)|CLR(LPUART_CTRL_LOOPS_MASK)|   \
/* ....   */ CLR(LPUART_CTRL_R8T9_MASK)|CLR(LPUART_CTRL_R9T8_MASK),                                 \
/* MODIR  */ SET(LPUART_MODIR_RTSWATER(0x0))|SET(LPUART_MODIR_TNP(0x0))|                            \
/* .....  */ CLR(LPUART_MODIR_IREN_MASK)|CLR(LPUART_MODIR_TXCTSSRC_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXCTSC_MASK)|CLR(LPUART_MODIR_RXRTSE_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXRTSPOL_MASK)|CLR(LPUART_MODIR_TXRTSE_MASK)|                         \
/* .....  */ CLR(LPUART_MODIR_TXCTSE_MASK)                                                          \
}
/***************************************************************************//*!
 * @brief   LPUART - DMA Mode.
 * @details Configures LPUART to operate in DMA mode. Receive data register
 *          full flag and transmit data register empty will cause DMA requests.
 * @param   brate     Baud rate.
 * @param   clk       Module clock in Hz.
 * @showinitializer
 ******************************************************************************/
#define LPUART_RDRF_TDRE_DMAMODE_CONFIG(brate, clk)                                                 \
(tLPUART) {                                                                                         \
/* PINCFG */ SET(LPUART_PINCFG_TRGSEL(0x0)),                                                        \
/* BAUD   */ SET(LPUART_BAUD_SBR(LPUART_CALC_SBR(brate,clk)))|                                      \
/* ....   */ SET(LPUART_BAUD_OSR(LPUART_OSR_FIXED))|                                                \
/* ....   */ CLR(LPUART_BAUD_MAEN1_MASK)|CLR(LPUART_BAUD_MAEN2_MASK)|CLR(LPUART_BAUD_M10_MASK)|     \
/* ....   */ SET(LPUART_BAUD_TDMAE_MASK)|SET(LPUART_BAUD_RDMAE_MASK)|SET(LPUART_BAUD_MATCFG(0x0))|  \
/* ....   */ CLR(LPUART_BAUD_BOTHEDGE_MASK)|CLR(LPUART_BAUD_RESYNCDIS_MASK)|                        \
/* ....   */ CLR(LPUART_BAUD_LBKDIE_MASK)|CLR(LPUART_BAUD_RXEDGIE_MASK)|CLR(LPUART_BAUD_SBNS_MASK), \
/* STAT   */ CLR(LPUART_STAT_MSBF_MASK)|CLR(LPUART_STAT_RXINV_MASK)|CLR(LPUART_STAT_RWUID_MASK)|    \
/* ....   */ CLR(LPUART_STAT_BRK13_MASK)|CLR(LPUART_STAT_LBKDE_MASK)|                               \
/* ....   */ CLR(LPUART_STAT_AME_MASK) |CLR(LPUART_STAT_LBKFE_MASK),                                \
/* CTRL   */ SET(LPUART_CTRL_RE_MASK)|SET(LPUART_CTRL_TE_MASK)|                                     \
/* ....   */ CLR(LPUART_CTRL_PT_MASK)|CLR(LPUART_CTRL_PE_MASK)|CLR(LPUART_CTRL_PEIE_MASK)|          \
/* ....   */ CLR(LPUART_CTRL_M_MASK) |CLR(LPUART_CTRL_M7_MASK)|SET(LPUART_CTRL_IDLECFG(0x0)) |      \
/* ....   */ CLR(LPUART_CTRL_MA1IE_MASK)|CLR(LPUART_CTRL_MA2IE_MASK)|CLR(LPUART_CTRL_ILIE_MASK)|    \
/* ....   */ SET(LPUART_CTRL_RIE_MASK)|CLR(LPUART_CTRL_TCIE_MASK)|SET(LPUART_CTRL_TIE_MASK)|        \
/* ....   */ CLR(LPUART_CTRL_FEIE_MASK)|CLR(LPUART_CTRL_NEIE_MASK)|CLR(LPUART_CTRL_ORIE_MASK) |     \
/* ....   */ CLR(LPUART_CTRL_TXINV_MASK)|CLR(LPUART_CTRL_TXDIR_MASK)|CLR(LPUART_CTRL_RSRC_MASK)|    \
/* ....   */ CLR(LPUART_CTRL_RWU_MASK)|CLR(LPUART_CTRL_SBK_MASK)|CLR(LPUART_CTRL_ILT_MASK)|         \
/* ....   */ CLR(LPUART_CTRL_WAKE_MASK)|CLR(LPUART_CTRL_DOZEEN_MASK)|CLR(LPUART_CTRL_LOOPS_MASK)|   \
/* ....   */ CLR(LPUART_CTRL_R8T9_MASK)|CLR(LPUART_CTRL_R9T8_MASK),                                 \
/* MODIR  */ SET(LPUART_MODIR_RTSWATER(0x0))|SET(LPUART_MODIR_TNP(0x0))|                            \
/* .....  */ CLR(LPUART_MODIR_IREN_MASK)|CLR(LPUART_MODIR_TXCTSSRC_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXCTSC_MASK)|CLR(LPUART_MODIR_RXRTSE_MASK)|                           \
/* .....  */ CLR(LPUART_MODIR_TXRTSPOL_MASK)|CLR(LPUART_MODIR_TXRTSE_MASK)|                         \
/* .....  */ CLR(LPUART_MODIR_TXCTSE_MASK)                                                          \
}
/*! @} End of lpuart_config */

/******************************************************************************
* LPUART interrupt request flags
*
*//*! @addtogroup lpuart_irqs
* @{
*******************************************************************************/
#define LPUART_MA2F     (uint32_t)(1UL << 14)  ///< Match 2 Flag
#define LPUART_MA1F     (uint32_t)(1UL << 15)  ///< Match 1 Flag
#define LPUART_PF       (uint32_t)(1UL << 16)  ///< Parity Error Flag
#define LPUART_FE       (uint32_t)(1UL << 17)  ///< Framing Error Flag
#define LPUART_NF       (uint32_t)(1UL << 18)  ///< Noise Flag
#define LPUART_OR       (uint32_t)(1UL << 19)  ///< Receiver Overrun Flag
#define LPUART_IDLE     (uint32_t)(1UL << 20)  ///< Idle Line Flag
#define LPUART_RDRF     (uint32_t)(1UL << 21)  ///< Receive Data Register Full Flag
#define LPUART_TC       (uint32_t)(1UL << 22)  ///< Transmission Complete Flag
#define LPUART_TDRE     (uint32_t)(1UL << 23)  ///< Transmit Data Register Empty Flag
#define LPUART_RXEDGIF  (uint32_t)(1UL << 30)  ///< RXD Pin Active Edge Interrupt Flag
#define LPUART_LBKDIF   (uint32_t)(1UL << 31)  ///< RXD Pin Active Edge Interrupt Flag
/*! @} End of lpuart_irqs                                                    */

/******************************************************************************
* LPUART interrupt request sources
*
*//*! @addtogroup lpuart_irq_sources
* @{
*******************************************************************************/
#define LPUART_MA2IE    (uint32_t)(1UL <<  14) ///< Match 2 Interrupt
#define LPUART_MA1IE    (uint32_t)(1UL <<  15) ///< Match 1 Interrupt
#define LPUART_ILIE     (uint32_t)(1UL <<  20) ///< Idle Line Interrupt
#define LPUART_RIE      (uint32_t)(1UL <<  21) ///< Receiver Interrupt
#define LPUART_TCIE     (uint32_t)(1UL <<  22) ///< Transmission Complete Interrupt
#define LPUART_TIE      (uint32_t)(1UL <<  23) ///< Transmit Interrupt
#define LPUART_PEIE     (uint32_t)(1UL <<  24) ///< Parity Error Interrupt
#define LPUART_FEIE     (uint32_t)(1UL <<  25) ///< Framing Error Interrupt
#define LPUART_NEIE     (uint32_t)(1UL <<  26) ///< Noise Error Interrupt
#define LPUART_ORIE     (uint32_t)(1UL <<  27) ///< Overrun Interrupt
/*! @} End of lpuart_irq_sources     */

/******************************************************************************
* LPUART DMA request sources
*
*//*! @addtogroup lpuart_dma
* @{
*******************************************************************************/
#define LPUART_TDMAE    (uint32_t)(1UL << 23) ///< Transmitter DMA
#define LPUART_RDMAE    (uint32_t)(1UL << 21) ///< Receiver Full DMA
/*! @} End of lpuart_dma */

/******************************************************************************
 * LPUART callback registered by LPUART_InstallCallback() function
 *//*! @addtogroup lpuart_callback
 * @{
*******************************************************************************/
/*! @brief tLPUART_CALLBACK_TYPE declaration                                  */
typedef enum
{
  MA2F_CALLBACK     = (uint32_t)(1UL << 14),  ///< Match 2 Flag
  MA1F_CALLBACK     = (uint32_t)(1UL << 15),  ///< Match 1 Flag
  PF_CALLBACK       = (uint32_t)(1UL << 16),  ///< Parity Error Flag
  FE_CALLBACK       = (uint32_t)(1UL << 17),  ///< Framing Error Flag
  NF_CALLBACK       = (uint32_t)(1UL << 18),  ///< Noise Flag
  OR_CALLBACK       = (uint32_t)(1UL << 19),  ///< Receiver Overrun Flag
  IDLE_CALLBACK     = (uint32_t)(1UL << 20),  ///< Idle Line Flag
  RDRF_CALLBACK     = (uint32_t)(1UL << 21),  ///< Receive Data Register Full Flag
  TC_CALLBACK       = (uint32_t)(1UL << 22),  ///< Transmission Complete Flag
  TDRE_CALLBACK     = (uint32_t)(1UL << 23),  ///< Transmit Data Register Empty Flag
  RXEDGIF_CALLBACK  = (uint32_t)(1UL << 30),  ///< RXD Pin Active Edge Interrupt Flag
  LBKDIF_CALLBACK   = (uint32_t)(1UL << 31)   ///< RXD Pin Active Edge Interrupt Flag
} tLPUART_CALLBACK_TYPE;

/*! @brief tLPUART_CALLBACK function declaration                              */
typedef void (*tLPUART_CALLBACK)(volatile LPUART_Type *module, tLPUART_CALLBACK_TYPE type);
/*! @} End of lpuart_callback                                                 */

/******************************************************************************
* LPUART function and macro definitions
*
*//*! @addtogroup lpuart_macro
* @{
*******************************************************************************/
/***************************************************************************//*!
 * @brief   Returns version numbers for the module design and feature set.
 * @details This macro returns version ID for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @return  @ref uint32_t  VERID register
 * @note    Implemented as a macro.
 * @see     @ref LPUART_GetPARAM
 ******************************************************************************/
#define LPUART_GetVERID(module)    module->VERID

/***************************************************************************//*!
 * @brief   Returns parameter values that were implemented in the module.
 * @details This macro returns parameter values for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @return  @ref uint32_t  PARAM register
 * @note    Implemented as a macro.
 * @see     @ref LPUART_GetVERID
 ******************************************************************************/
#define LPUART_GetPARAM(module)    module->PARAM

/***************************************************************************//*!
 * @brief   Reset Module.
 * @details This macro resets all internal logic and registers for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define LPUART_Reset(module)    do{ module->GLOBAL |= LPUART_GLOBAL_RST_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enable DMA request.
 * @details Enables DMA request for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @param   mask        Mask of @ref lpuart_dma.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_DisableDma
 ******************************************************************************/
#define LPUART_EnableDma(module,mask)    do{ module->BAUD |= mask; }while(0)

/***************************************************************************//*!
 * @brief   Disable DMA request.
 * @details Disables DMA request for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @param   mask        Mask of @ref lpuart_dma.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_EnableDma
 ******************************************************************************/
#define LPUART_DisableDma(module,mask)    do{ module->BAUD &= ~(mask); }while(0)

/***************************************************************************//*!
 * @brief   Enable LPUART transmitter.
 * @details This macro enables LPUART transmitter for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_DisableTx
 ******************************************************************************/
#define LPUART_EnableTx(module)    do{ module->CTRL |= LPUART_CTRL_TE_MASK ; }while(0)

/***************************************************************************//*!
 * @brief   Disable LPUART transmitter.
 * @details This macro disables LPUART transmitter for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_EnableTx
 ******************************************************************************/
#define LPUART_DisableTx(module)    do{ module->CTRL &= ~LPUART_CTRL_TE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enable LPUART receiver.
 * @details This macro enables LPUART receiver for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_DisableRx
 ******************************************************************************/
#define LPUART_EnableRx(module)    do{ module->CTRL |= LPUART_CTRL_RE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disable LPUART receiver.
 * @details This macro disables LPUART receiver for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_EnableRx
 ******************************************************************************/
#define LPUART_DisableRx(module)    do{ module->CTRL &= ~LPUART_CTRL_RE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Returns interrupt flags.
 * @details This macro returns interrupt flags for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @return  Mask of @ref lpuart_irqs.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_ClrIrqFlags
 ******************************************************************************/
#define LPUART_GetIrqFlags(module)    module->STAT

/***************************************************************************//*!
 * @brief   Clears interrupt flags.
 * @details This macro clears interrupt flags given by mask parameter
 *          for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @param   mask        Mask of @ref lpuart_irqs.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_GetIrqFlags
 ******************************************************************************/
#define LPUART_ClrIrqFlags(module,mask)    do{ module->STAT = mask; }while(0)

/***************************************************************************//*!
 * @brief   Returns and clears all interrupt flags with the
 *          driver format @ref lpuart_callback
 * @details This macro returns and clears all interrupt flags
 *          for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @return  Mask of @ref lpuart_irqs.
 * @note    Implemented as a macro.
 * @see     @ref lpuart_irqs.
 ******************************************************************************/
#define LPUART_GetClrIrqFlags(module)                 \
({                                                    \
  register uint32_t __r = LPUART_GetIrqFlags(module); \
  LPUART_ClrIrqFlags(module, __r);                    \
  __r;                                                \
})

/***************************************************************************//*!
 * @brief   Enable interrupt request.
 * @details Enables interrupt request for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @param   mask        Mask of @ref lpuart_irq_sources.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_DisableIrq
 ******************************************************************************/
#define LPUART_EnableIrq(module,mask)    do{ module->CTRL |= mask; }while(0)

/***************************************************************************//*!
 * @brief   Disable interrupt request.
 * @details Disables interrupt request for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @param   mask        Mask of @ref lpuart_irq_sources.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_EnableIrq
 ******************************************************************************/
#define LPUART_DisableIrq(module,mask)    do{ module->CTRL &= ~(mask); }while(0)

/***************************************************************************//*!
 * @brief   Disables hardware parity on LPUART.
 * @details This macro disables hardware parity generation and checking.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_SetEvenParity, @ref LPUART_SetOddParity,
 *          @ref LPUART_ParityEnable
 ******************************************************************************/
#define LPUART_ParityDisable(module)    do{ module->CTRL &= ~LPUART_CTRL_PE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables hardware parity on LPUART.
 * @details This macro enables hardware parity generation and checking.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_ParityDisable, @ref LPUART_SetOddParity
 *          @ref LPUART_SetEvenParity
 ******************************************************************************/
#define LPUART_ParityEnable(module)   do{ module->CTRL |= LPUART_CTRL_PE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables odd parity.
 * @details This macro selects odd parity when the HW parity is enabled.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_ParityDisable, @ref LPUART_ParityEnable
 *          @ref LPUART_SetEvenParity
 ******************************************************************************/
#define LPUART_SetOddParity(module)   do{ module->CTRL |= LPUART_CTRL_PT_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables even parity.
 * @details This macro selects even parity when the HW parity is enabled
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_ParityDisable, @ref LPUART_ParityEnable
 *          @ref LPUART_SetOddParity
 ******************************************************************************/
#define LPUART_SetEvenParity(module)  do{ module->CTRL &= ~LPUART_CTRL_PT_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables 9-bit mode.
 * @details This macro enables receiver and transmitter to use 9-bit data
 *          characters.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_Set8BitMode, @ref LPUART_Set7BitMode
 ******************************************************************************/
#define LPUART_Set9BitMode(module)    do{ module->CTRL &= ~LPUART_CTRL_M7_MASK; \
                                          module->CTRL |= LPUART_CTRL_M_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables 8-bit mode.
 * @details This macro enables receiver and transmitter to use 8-bit data
 *          characters.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_Set9BitMode, @ref LPUART_Set7BitMode
 ******************************************************************************/
#define LPUART_Set8BitMode(module)    do{ module->CTRL &= ~LPUART_CTRL_M7_MASK; \
                                          module->CTRL &= ~LPUART_CTRL_M_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables 7-bit mode.
 * @details This macro enables receiver and transmitter to use 7-bit data
 *          characters.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_Set9BitMode, @ref LPUART_Set8BitMode
 ******************************************************************************/
#define LPUART_Set7BitMode(module)    do{ module->CTRL |= LPUART_CTRL_M7_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disables MSB bit first.
 * @details This macro disables MSB bit first. The LSB (bit0) is the 1st bit
 *          that is transmitted following the start bit.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_MSBFirstEnable
 ******************************************************************************/
#define LPUART_MSBFirstDisable(module)    do{ module->STAT &= ~LPUART_STAT_MSBF_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables MSB bit first.
 * @details This macro enables MSB bit first. The MSB (bit 9,8,7 or 6) is the
 *          1st bit transmitted following the start bit.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_MSBFirstDisable
 ******************************************************************************/
#define LPUART_MSBFirstEnable(module)    do{ module->STAT |= LPUART_STAT_MSBF_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disables receive data inversion.
 * @details This macro disables receive data inversion.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_RxInvEnable
 ******************************************************************************/
#define LPUART_RxInvDisable(module)    do{ module->STAT &= ~LPUART_STAT_RXINV_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables receive data inversion.
 * @details This macro enables receive data inversion.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_RxInvDisable
 ******************************************************************************/
#define LPUART_RxInvEnable(module)    do{ module->STAT |= LPUART_STAT_RXINV_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables long Break character generation.
 * @details This macro enables long Break character generation. The Break
 *          character with length of 13 bit times is transmitted.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_LongBreakCharDisable
 ******************************************************************************/
#define LPUART_LongBreakCharEnable(module)    do{ module->STAT |= LPUART_STAT_BRK13_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disables long Break character generation.
 * @details This macro disables long Break character generation. The Break
 *          character with length of 10 bit times is transmitted.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_LongBreakCharEnable
 ******************************************************************************/
#define LPUART_LongBreakCharDisable(module)    do{ module->STAT &= ~LPUART_STAT_BRK13_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disables LIN Break Detection.
 * @details This macro disables a longer break character detection length.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_LINBreakEnable
 ******************************************************************************/
#define LPUART_LINBreakDisable(module)    do{ module->STAT &= ~LPUART_STAT_LBKDE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Enables LIN Break Detection.
 * @details This macro enables a longer break character detection length.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_LINBreakDisable
 ******************************************************************************/
#define LPUART_LINBreakEnable(module)    do{ module->STAT |= LPUART_STAT_LBKDE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Reads and returns transmitter state.
 * @details This macro returns transmitter state of the specified module.
 * @param   module      One of @ref lpuart_modules.
 * @return  true (non-zero) transmitter idle,
 * @return  false           transmitter active.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_RxFull, @ref LPUART_TxComplete, @ref LPUART_ClrIrqFlags
 ******************************************************************************/
#define LPUART_TxIdle(module)    (module->STAT & LPUART_STAT_TDRE_MASK)

/***************************************************************************//*!
 * @brief   Reads and returns receiver state.
 * @details This macro returns receiver state of the specified module.
 * @param   module      One of @ref lpuart_modules.
 * @return  true (non-zero) character ready,
 * @return  false           receiver busy.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_TxIdle, @ref LPUART_TxComplete, @ref LPUART_ClrIrqFlags
 ******************************************************************************/
#define LPUART_RxFull(module)    (module->STAT & LPUART_STAT_RDRF_MASK)

/***************************************************************************//*!
 * @brief   Returns transfer complete state.
 * @details This macro returns transfer complete state.
 * @param   module      One of @ref lpuart_modules.
 * @return  true (non-zero) character transmit complete,
 * @return  false           character transmit non-complete.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_TxIdle, @ref LPUART_RxFull, @ref LPUART_ClrIrqFlags
 ******************************************************************************/
#define LPUART_TxComplete(module)    (module->STAT & LPUART_STAT_TC_MASK)

/***************************************************************************//*!
 * @brief   Reads and returns received character.
 * @details This macro reads character received by the specified module.
 * @param   module      One of @ref lpuart_modules.
 * @return  @ref int8_t received character.
 * @note    Implemented as a macro.
 * @warning Doesn't wait for a new byte (until RDRF is set). Insert
 *          <c>while(!LPUART_RxFull(LPUART?));</c> statement prior this macro
 *          to ensure new byte is returned.
 * @see     @ref LPUART_PutChar, @ref LPUART_PutStr, @ref LPUART_Rd,
 *          @ref LPUART_GetData, @ref LPUART_PutData, @ref LPUART_Wr
 ******************************************************************************/
#define LPUART_GetChar(module)    (module->DATA & 0xFF)

/***************************************************************************//*!
 * @brief   Sends character.
 * @details This macro sends character to the specified module.
 * @param   module      One of @ref lpuart_modules.
 * @param   c       Character.
 * @note    Implemented as a macro.
 * @warning Doesn't wait until character is sent. Insert
 *          <c>while(!LPUART_TxIdle(LPUART?));</c> statement prior this macro to
 *          ensure transmitter is idle and able to send new character.
 * @see     @ref LPUART_GetChar, @ref LPUART_PutStr, @ref LPUART_Rd,
 *          @ref LPUART_GetChar, @ref LPUART_PutData, @ref LPUART_Wr
 ******************************************************************************/
#define LPUART_PutChar(module,c)    do{ module->DATA = c; }while(0)

/***************************************************************************//*!
 * @brief   Reads and returns 10-bits data.
 * @details This macro reads character received by the specified module.
 * @param   module        One of @ref lpuart_modules.
 * @return  @ref int16_t  received 16 bit word.
 * @note    Implemented as a macro.
 * @warning Doesn't wait for a new byte (until RDRF is set). Insert
 *          <c>while(!LPUART_RxFull(LPUART?));</c> statement prior this macro
 *          to ensure new byte is returned.
 * @see     @ref LPUART_PutChar, @ref LPUART_PutStr, @ref LPUART_Rd,
 *          @ref LPUART_GetChar, @ref LPUART_PutData, @ref LPUART_Wr
 ******************************************************************************/
#define LPUART_GetData(module)    (module->DATA & 0x3FF)

/***************************************************************************//*!
 * @brief   Sends data.
 * @details This macro sends data to the specified module.
 * @param   module      One of @ref lpuart_modules.
 * @param   c       10-bit data to be sent.
 * @note    Implemented as a macro.
 * @warning FRETSC (Frame Error / Transmit Special Character) bit is affected.
 * @see     @ref LPUART_PutChar, @ref LPUART_PutStr, @ref LPUART_Rd,
 *          @ref LPUART_GetChar, @ref LPUART_GetData, @ref LPUART_Wr
 ******************************************************************************/
#define LPUART_PutData(module,c)    do{ module->DATA = c; }while(0)

/***************************************************************************//*!
 * @brief   Sends string.
 * @details This macro sends string to the specified module.
 * @param   module      One of @ref lpuart_modules.
 * @param   str     String terminated by null character.
 * @note    Implemented as a macro.
 * @warning Doesn't terminate until NULL character is read.
 * @see     @ref LPUART_GetChar, @ref LPUART_PutChar, @ref LPUART_Rd,
 *          @ref LPUART_GetData, @ref LPUART_PutData, @ref LPUART_Wr
 ******************************************************************************/
#define LPUART_PutStr(module,str)   do{                                       \
                                      register int __t=0;                     \
                                      while(str[__t] != 0)                    \
                                      {                                       \
                                        while (!(LPUART_TxIdle(module)));     \
                                        LPUART_PutChar(module,str[__t]);      \
                                        __t++;                                \
                                      }                                       \
                                      while (!(LPUART_TxComplete(module)));   \
                                    }while(0)

/***************************************************************************//*!
 * @brief   Reads <c>count</c> bytes and stores them in a <c>buffer</c>.
 * @details This macro reads <c>count</c> bytes from specified module and
 *          stores them in <c>buffer</c>. Returns when <c>count</c> bytes have
 *          been read.
 * @param   module      One of @ref lpuart_modules.
 * @param   buffer  @ref uint8_t [] specifies the variable in which to store the
 *                  data that was read from the selected module.
 * @param   count   Specifies the number of bytes to read from the selected
 *                    module.
 * @note    Implemented as a macro.
 * @warning Doesn't terminate until <c>count</c> bytes are read.
 * @see     @ref LPUART_GetChar, @ref LPUART_PutChar, @ref LPUART_PutStr,
 *          @ref LPUART_GetData, @ref LPUART_PutData, @ref LPUART_Wr
 ******************************************************************************/
#define LPUART_Rd(module,buffer,count)                                        \
do{                                                                           \
  register int __t=0;                                                         \
  while (__t < count)                                                         \
  {                                                                           \
    while (!(LPUART_RxFull(module))); /* wait until new byte is available  */ \
    buffer[__t++] = module->DATA;     /* read and store new byte           */ \
  }                                                                           \
}while(0)

 /***************************************************************************//*!
  * @brief   Writes <c>count</c> bytes from <c>buffer</c>.
  * @details This macro writes <c>count</c> bytes from <c>buffer</c> to the
  *          specified module. Returns when <c>count</c> bytes are written.
 * @param   module      One of @ref lpuart_modules.
  * @param   buffer  @ref uint8_t [] specifies the variable from which to read
  *                  the data that will be written to the selected module.
  * @param   count   Specifies the number of bytes to write to the selected
  *                  module.
  * @note    Implemented as a  macro.
  * @see     @ref LPUART_GetChar, @ref LPUART_PutChar, @ref LPUART_PutStr,
  *          @ref LPUART_GetData, @ref LPUART_PutData, @ref LPUART_Rd
  ******************************************************************************/
#define LPUART_Wr(module,buffer,count)                                         \
do{                                                                            \
  register int __t=0;                                                          \
  while (__t < count)                                                          \
  {                                                                            \
    while(!(LPUART_TxIdle(module))); /* wait until transmitter is idle     */  \
    module->DATA = buffer[__t++];    /* write new byte                     */  \
  }                                                                            \
  while(!(LPUART_TxIdle(module)));   /* wait until last character is sent  */  \
}while(0)

/***************************************************************************//*!
 * @brief   Queues a break character.
 * @details Queues in the transmit data stream for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define LPUART_SendBreak(module) do{ module->CTRL |= LPUART_CTRL_SBK_MASK;  \
                                     module->CTRL &= ~LPUART_CTRL_SBK_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disables match address mode.
 * @details This macro disables match address mode.
 * @param   module      One of @ref lpuart_modules.
 * @note    Implemented as a macro.
 * @see     @ref LPUART_SetMatch1, @ref LPUART_SetMatch2
 ******************************************************************************/
#define LPUART_MatchAddrDisable(module)                                       \
do{                                                                           \
  module->BAUD &= ~(LPUART_BAUD_MAEN1_MASK|LPUART_BAUD_MAEN2_MASK);           \
  module->MATCH = 0x00;                                                       \
}while(0)

/***************************************************************************//*!
 * @brief   Set Match Address 1.
 * @details This macro sets Match Address 1 for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @param   match       MA1 value (@ref uint16_t).
 * @note    Implemented as a macro.
 ******************************************************************************/
#define LPUART_SetMatch1(module,match)           \
do{ module->BAUD |= LPUART_BAUD_MAEN1_MASK;      \
    module->MATCH &= ~LPUART_MATCH_MA1_MASK;     \
    module->MATCH |= LPUART_MATCH_MA1(match); }while(0)

/***************************************************************************//*!
 * @brief   Set Match Address 2.
 * @details This macro sets Match Address 2 for source given by argument.
 * @param   module      One of @ref lpuart_modules.
 * @param   match       MA2 value (@ref uint16_t).
 * @note    Implemented as a macro.
 ******************************************************************************/
#define LPUART_SetMatch2(module,match)           \
do{ module->BAUD |= LPUART_BAUD_MAEN2_MASK;      \
    module->MATCH &= ~LPUART_MATCH_MA2_MASK;     \
    module->MATCH |= LPUART_MATCH_MA2(match); }while(0)

/***************************************************************************//*!
 * @brief   Enables/disables internal loop mode.
 * @details This macro enables/disables internal loop mode for the specified
 *          module. When loop mode is set, the RxD pin is disconnected from the
 *          LPUART and the transmitter output is internally connected to the
 *          receiver input. The transmitter and the receiver must be enabled to
 *          use the loop function.
 * @param   module      One of @ref lpuart_modules.
 * @param   ctrl    TRUE (loopback mode enabled, receiver input is internally
 *                        connected to transmitter output)\n
 *                  FALSE (normal operation).
 * @note    Implemented as a macro.
 ******************************************************************************/
#define LPUART_LoopModeCtrl(module,ctrl)                                      \
do{                                                                           \
  if (ctrl)                                                                   \
  {                                                                           \
    module->CTRL |= LPUART_CTRL_LOOPS_MASK;                                   \
    module->CTRL &= ~LPUART_CTRL_RSRC_MASK;                                   \
  }                                                                           \
  else                                                                        \
    module->CTRL &= ~LPUART_CTRL_LOOPS_MASK;                                  \
}while(0)

/***************************************************************************//*!
 * @brief   LPUART initialization
 * @details This function initializes selected LPUART.
 * @param   module      One of @ref lpuart_modules.
 * @param   cfg         One of @ref lpuart_config.
 * @note    Implemented as a function call. Use with constant arguments
 * @see     @ref LPUART_InstallCallback
 ******************************************************************************/
#define LPUART_Init(module,cfg)    LPUART_prvInit(module,cfg)

/***************************************************************************//*!
 * @brief   Installs callback function for interrupt vector depended on LPUART module.
 * @details This function install callback function for interrupt vector depended
 *          on LPUART module.
 * @param   module One of @ref lpuart_modules.
 * @param   ip     @ref irq_prilvl "Interrupt Priority Levels".
 * @param   callback  Pointer to the @ref lpuart_callback.
 * @note    Implemented as a function call. Use with constant arguments.
 * @see     @ref LPUART_Init, @ref LPUART_EnableIrq
 ******************************************************************************/
#define LPUART_InstallCallback(module,ip,callback) module##_InstallCallback (ip,callback)
/*! @} End of lpuart_macro */

/******************************************************************************
 * public function prototypes                                                 *
 ******************************************************************************/
void LPUART_prvInit (volatile LPUART_Type *module, tLPUART cfg);

void LPUART0_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART1_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART2_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART3_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART4_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART5_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART6_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART7_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART8_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART9_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART10_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART11_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART12_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART13_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART14_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);
void LPUART15_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback);

/******************************************************************************
 * interrupt handler prototypes                                               *
 ******************************************************************************/
void LPUART0_Handler  (void);
void LPUART1_Handler  (void);
void LPUART2_Handler  (void);
void LPUART3_Handler  (void);
void LPUART4_Handler  (void);
void LPUART5_Handler  (void);
void LPUART6_Handler  (void);
void LPUART7_Handler  (void);
void LPUART8_Handler  (void);
void LPUART9_Handler  (void);
void LPUART10_Handler (void);
void LPUART11_Handler (void);
void LPUART12_Handler (void);
void LPUART13_Handler (void);
void LPUART14_Handler (void);
void LPUART15_Handler (void);

#endif /* __LPUART_H */
