/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      clock.h
 * @brief     Clock Generation Module (MC_CGM), Fast Internal RC Oscillator
 *            (FIRC), Slow Internal RC Oscillator (SIRC), Fast Crystal
 *            Oscillator Digital Controller (FIRC), Slow Crystal Oscillator
 *            Digital Controller (SIRC), and PLL Digital Interface (PLLDIG)
 *            driver header file.
 */
#ifndef __CLOCK_H
#define __CLOCK_H

/******************************************************************************
 * Configuration structure definition                                         *
 ******************************************************************************/
typedef struct
{
  uint32_t CTL;
  uint32_t PRAMC0_PRCR1;
  uint32_t PRAMC1_PRCR1;
  uint32_t PRAMC2_PRCR1;
  uint32_t CONFIG_REG_GPR;
  uint32_t FXOSC_CTRL;
  uint32_t STDBY_ENABLE;
  uint32_t MISCELLANEOUS_IN;
  uint32_t PLLDV;
  uint32_t PLLFD;
  uint32_t PLLFM;
  uint32_t PLLODIV0;
  uint32_t PLLODIV1;
  uint32_t MUX_0_DC_0;
  uint32_t MUX_0_DC_1;
  uint32_t MUX_0_DC_2;
  uint32_t MUX_0_DC_3;
  uint32_t MUX_0_DC_4;
  uint32_t MUX_0_CSC;
} tCLOCK_CONFIG;

/******************************************************************************
* CLOCK multiplexer clock switch status
*
*//*! @addtogroup clock_api_return
* @{
*******************************************************************************/
/*! tCLOCK_SW_STATUS type declaration                                         */
typedef enum
{
  CLOCK_SW_SUCCESS = 1U,            ///< Clock switch succeeded
  CLOCK_SW_TGT_CLK_INACTIVE = 2U,   ///< Clock switch failed due to inactive target clock, current clock is FIRC
  CLOCK_SW_CURR_CLK_INACTIVE = 3U   ///< Clock switch failed due to inactive current clock, current clock is FIRC
} tCLOCK_SW_STATUS;
/*! @} End of clock_api_return                                                */

/******************************************************************************
* CLOCK default configurations used by CLOCK_Init()
*
*//*! @addtogroup clock_config
* @{
*******************************************************************************/
/* XTAL specific PLL reference divider settings                                                    */
#if configXTAL_FREQ == 0
#define CLOCK_PLL_PLLDV_RDIV        0u  /* No external crystal                                     */
#elif configXTAL_FREQ == 1
#define CLOCK_PLL_PLLDV_RDIV        2u  /* XTAL @8MHz  -> PLLDV[RDIV] = 2  -> fpll_ref/RDIV = 4MHz */
#define CLOCK_PLL_PLLDV_MFI         240 /* -> fpll_ref/RDIV*MFI = 960MHz                           */
#elif configXTAL_FREQ == 2
#define CLOCK_PLL_PLLDV_RDIV        4u  /* XTAL @16MHz -> PLLDV[RDIV] = 4  -> fpll_ref/RDIV = 4MHz */
#define CLOCK_PLL_PLLDV_MFI         240 /* -> fpll_ref/RDIV*MFI = 960MHz                           */
#elif configXTAL_FREQ == 3
#define CLOCK_PLL_PLLDV_RDIV        5u  /* XTAL @20MHz -> PLLDV[RDIV] = 5  -> fpll_ref/RDIV = 4MHz */
#define CLOCK_PLL_PLLDV_MFI         240 /* -> fpll_ref/RDIV*MFI = 960MHz                           */
#elif configXTAL_FREQ == 4
#define CLOCK_PLL_PLLDV_RDIV        6u  /* XTAL @24MHz -> PLLDV[RDIV] = 6  -> fpll_ref/RDIV = 4MHz */
#define CLOCK_PLL_PLLDV_MFI         240 /* -> fpll_ref/RDIV*MFI = 960MHz                           */
#elif configXTAL_FREQ == 5
#define CLOCK_PLL_PLLDV_RDIV        4u  /* XTAL @32MHz -> PLLDV[RDIV] = 4  -> fpll_ref/RDIV = 8MHz */
#define CLOCK_PLL_PLLDV_MFI         120 /* -> fpll_ref/RDIV*MFI = 960MHz                           */
#elif configXTAL_FREQ == 6
#define CLOCK_PLL_PLLDV_RDIV        5u  /* XTAL @40MHz -> PLLDV[RDIV] = 5  -> fpll_ref/RDIV = 8MHz */
#define CLOCK_PLL_PLLDV_MFI         120 /* -> fpll_ref/RDIV*MFI = 960MHz                           */
#endif

/* CLOCK_MODE_3_CONFIG SRAM wait state config.                                                     */
#define CLOCK_PRAMC_PRCR1_FT_DIS    CLR(PRAMC_PRCR1_FT_DIS_MASK) /* 0 SRAM wait states             */
/* CLOCK_MODE_3_CONFIG & CLOCK_MODE_2_CONFIG PLL config.                                           */
#define CLOCK_PLL_PLLDV_ODIV2       4u  /* PLL_ODIV2_CLK = PLL_VCO_CLK / 4                         */
#define CLOCK_PLL_PLLODIV1          4u  /* PLL_PHI1_CLK = PLL[ODIV2] / 5                           */
/* CLOCK_MODE_3_CONFIG PLL config.                                                                 */
#define CLOCK_PLL_PLLODIV0_120      1u  /* PLL_PHI0_CLK = PLL[ODIV2] / 2                           */
/* CLOCK_MODE_2_CONFIG PLL config.                                                                 */
#define CLOCK_PLL_PLLODIV0_80       2u  /* PLL_PHI0_CLK = PLL[ODIV2] / 3                           */

/***************************************************************************//*!
 * @brief Configures device clocks.
 * @details Configures device clocks and memory wait states as shown below.
 *
 * Clock sources:
 * |Clock source  |Frequency in MHz |
 * |:------------:|:---------------:|
 * |FXOSC         |ON               |
 * |FIRC          |48               |
 * |PLL_VCO_CLK   |960              |
 * |PLL_ODIV2_CLK |480              |
 * |PLL_PHI0_CLK  |240              |
 * |PLL_PHI1_CLK  |240              |
 *
 * MC_CGM MUX0 output clocks:
 * |Clock         |Frequency in MHz |
 * |:------------:|:---------------:|
 * |CORE_CLK      |240              |
 * |AIPS_PLAT_CLK |120              |
 * |AIPS_SLOW_CLK |60               |
 * |HSE_CLK       |120              |
 * |DCM_CLK       |60               |
 * |LBIST_CLK     |60               |
 * |QSPI_MEM_CLK  |120              |
 *
 * Memory wait states:
 * |Memory       |Wait states |
 * |:-----------:|:----------:|
 * |Flash        |7           |
 * |SRAM (read)  |1           |
 *
 * @showinitializer
 ******************************************************************************/
#define CLOCK_MODE_5_CONFIG                                                                \
(tCLOCK_CONFIG){                                                                           \
/* FLASH_CTL        */ CLR(FLASH_CTL_RWSL_MASK)|SET(FLASH_CTL_RWSC(7u)),                   \
/* PRAMC0_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|SET(PRAMC_PRCR1_FT_DIS_MASK),       \
/* PRAMC1_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|SET(PRAMC_PRCR1_FT_DIS_MASK),       \
/* PRAMC2_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|SET(PRAMC_PRCR1_FT_DIS_MASK),       \
/* CONFIG_REG_GPR   */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_APP_CORE_ACC(5u))|             \
/* ...              */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_FIRC_DIV_SEL(3u)),             \
/* FXOSC_CTRL       */ CLR(FXOSC_CTRL_OSC_BYP_MASK)|SET(FXOSC_CTRL_COMP_EN_MASK)|          \
/* ...              */ SET(FXOSC_CTRL_EOCV(157u))|SET(FXOSC_CTRL_GM_SEL(12u))|             \
/* ...              */ SET(FXOSC_CTRL_OSCON_MASK),                                         \
/* STDBY_ENABLE     */ SET(FIRC_STDBY_ENABLE_STDBY_EN_MASK),                               \
/* MISCELLANEOUS_IN */ SET(SIRC_MISCELLANEOUS_IN_STANDBY_ENABLE_MASK),                     \
/* PLLDV            */ SET(PLL_PLLDV_ODIV2(2u))|SET(PLL_PLLDV_RDIV(CLOCK_PLL_PLLDV_RDIV))| \
/* ...              */ SET(PLL_PLLDV_MFI(CLOCK_PLL_PLLDV_MFI)),                            \
/* PLLFD            */ CLR(PLL_PLLFD_SDMEN_MASK)|CLR(PLL_PLLFD_SDM2_MASK)|                 \
/* ...              */ CLR(PLL_PLLFD_SDM3_MASK)|CLR(PLL_PLLFD_MFN_MASK),                   \
/* PLLFM            */ SET(PLL_PLLFM_SSCGBYP_MASK)|CLR(PLL_PLLFM_SPREADCTL_MASK)|          \
/* ...              */ CLR(PLL_PLLFM_STEPSIZE_MASK)|CLR(PLL_PLLFM_STEPNO_MASK),            \
/* PLLODIV0         */ SET(PLL_PLLODIV_DIV(1u)),                                           \
/* PLLODIV1         */ SET(PLL_PLLODIV_DIV(1u)),                                           \
/* MUX_0_DC_0       */ SET(MC_CGM_MUX_0_DC_0_DIV(0u))|SET(MC_CGM_MUX_0_DC_0_DE_MASK),      \
/* MUX_0_DC_1       */ SET(MC_CGM_MUX_0_DC_1_DIV(1u))|SET(MC_CGM_MUX_0_DC_1_DE_MASK),      \
/* MUX_0_DC_2       */ SET(MC_CGM_MUX_0_DC_2_DIV(3u))|SET(MC_CGM_MUX_0_DC_2_DE_MASK),      \
/* MUX_0_DC_3       */ SET(MC_CGM_MUX_0_DC_3_DIV(1u))|SET(MC_CGM_MUX_0_DC_3_DE_MASK),      \
/* MUX_0_DC_4       */ SET(MC_CGM_MUX_0_DC_4_DIV(3u))|SET(MC_CGM_MUX_0_DC_4_DE_MASK),      \
/* MUX_0_CSC        */ SET(MC_CGM_MUX_0_CSC_SELCTL(8u))|SET(MC_CGM_MUX_0_CSC_CLK_SW_MASK)  \
}

/***************************************************************************//*!
 * @brief Configures device clocks.
 * @details Configures device clocks and memory wait states as shown below.
 *
 * Clock sources:
 * |Clock source  |Frequency in MHz |
 * |:------------:|:---------------:|
 * |FXOSC         |ON               |
 * |FIRC          |48               |
 * |PLL_VCO_CLK   |960              |
 * |PLL_ODIV2_CLK |480              |
 * |PLL_PHI0_CLK  |160              |
 * |PLL_PHI1_CLK  |240              |
 *
 * MC_CGM MUX0 output clocks:
 * |Clock         |Frequency in MHz |
 * |:------------:|:---------------:|
 * |CORE_CLK      |160              |
 * |AIPS_PLAT_CLK |80               |
 * |AIPS_SLOW_CLK |40               |
 * |HSE_CLK       |80               |
 * |DCM_CLK       |40               |
 * |LBIST_CLK     |40               |
 * |QSPI_MEM_CLK  |120              |
 *
 * Memory wait states:
 * |Memory       |Wait states |
 * |:-----------:|:----------:|
 * |Flash        |4           |
 * |SRAM (read)  |1           |
 *
 * @showinitializer
 ******************************************************************************/
#define CLOCK_MODE_4_CONFIG                                                                \
(tCLOCK_CONFIG){                                                                           \
/* FLASH_CTL        */ CLR(FLASH_CTL_RWSL_MASK)|SET(FLASH_CTL_RWSC(4u)),                   \
/* PRAMC0_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|SET(PRAMC_PRCR1_FT_DIS_MASK),       \
/* PRAMC1_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|SET(PRAMC_PRCR1_FT_DIS_MASK),       \
/* PRAMC2_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|SET(PRAMC_PRCR1_FT_DIS_MASK),       \
/* CONFIG_REG_GPR   */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_APP_CORE_ACC(5u))|             \
/* ...              */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_FIRC_DIV_SEL(3u)),             \
/* FXOSC_CTRL       */ CLR(FXOSC_CTRL_OSC_BYP_MASK)|SET(FXOSC_CTRL_COMP_EN_MASK)|          \
/* ...              */ SET(FXOSC_CTRL_EOCV(157u))|SET(FXOSC_CTRL_GM_SEL(12u))|             \
/* ...              */ SET(FXOSC_CTRL_OSCON_MASK),                                         \
/* STDBY_ENABLE     */ SET(FIRC_STDBY_ENABLE_STDBY_EN_MASK),                               \
/* MISCELLANEOUS_IN */ SET(SIRC_MISCELLANEOUS_IN_STANDBY_ENABLE_MASK),                     \
/* PLLDV            */ SET(PLL_PLLDV_ODIV2(2u))|SET(PLL_PLLDV_RDIV(CLOCK_PLL_PLLDV_RDIV))| \
/* ...              */ SET(PLL_PLLDV_MFI(CLOCK_PLL_PLLDV_MFI)),                            \
/* PLLFD            */ CLR(PLL_PLLFD_SDMEN_MASK)|CLR(PLL_PLLFD_SDM2_MASK)|                 \
/* ...              */ CLR(PLL_PLLFD_SDM3_MASK)|CLR(PLL_PLLFD_MFN_MASK),                   \
/* PLLFM            */ SET(PLL_PLLFM_SSCGBYP_MASK)|CLR(PLL_PLLFM_SPREADCTL_MASK)|          \
/* ...              */ CLR(PLL_PLLFM_STEPSIZE_MASK)|CLR(PLL_PLLFM_STEPNO_MASK),            \
/* PLLODIV0         */ SET(PLL_PLLODIV_DIV(2u)),                                           \
/* PLLODIV1         */ SET(PLL_PLLODIV_DIV(1u)),                                           \
/* MUX_0_DC_0       */ SET(MC_CGM_MUX_0_DC_0_DIV(0u))|SET(MC_CGM_MUX_0_DC_0_DE_MASK),      \
/* MUX_0_DC_1       */ SET(MC_CGM_MUX_0_DC_1_DIV(1u))|SET(MC_CGM_MUX_0_DC_1_DE_MASK),      \
/* MUX_0_DC_2       */ SET(MC_CGM_MUX_0_DC_2_DIV(3u))|SET(MC_CGM_MUX_0_DC_2_DE_MASK),      \
/* MUX_0_DC_3       */ SET(MC_CGM_MUX_0_DC_3_DIV(1u))|SET(MC_CGM_MUX_0_DC_3_DE_MASK),      \
/* MUX_0_DC_4       */ SET(MC_CGM_MUX_0_DC_4_DIV(3u))|SET(MC_CGM_MUX_0_DC_4_DE_MASK),      \
/* MUX_0_CSC        */ SET(MC_CGM_MUX_0_CSC_SELCTL(8u))|SET(MC_CGM_MUX_0_CSC_CLK_SW_MASK)  \
}

/***************************************************************************//*!
 * @brief Configures device clocks.
 * @details Configures device clocks and memory wait states as shown below.
 *
 * Clock sources:
 * |Clock source  |Frequency in MHz |
 * |:------------:|:---------------:|
 * |FXOSC         |ON               |
 * |FIRC          |48               |
 * |PLL_VCO_CLK   |960              |
 * |PLL_ODIV2_CLK |240              |
 * |PLL_PHI0_CLK  |120              |
 * |PLL_PHI1_CLK  |48               |
 *
 * MC_CGM MUX0 output clocks:
 * |Clock         |Frequency in MHz |
 * |:------------:|:---------------:|
 * |CORE_CLK      |120              |
 * |AIPS_PLAT_CLK |60               |
 * |AIPS_SLOW_CLK |30               |
 * |HSE_CLK       |120              |
 * |DCM_CLK       |30               |
 * |LBIST_CLK     |30               |
 * |QSPI_MEM_CLK  |120              |
 *
 * Memory wait states:
 * |Memory       |Wait states |
 * |:-----------:|:----------:|
 * |Flash        |3           |
 * |SRAM (read)  |0           |
 *
 * @showinitializer
 ******************************************************************************/
#define CLOCK_MODE_3_CONFIG                                                                \
(tCLOCK_CONFIG){                                                                           \
/* FLASH_CTL        */ CLR(FLASH_CTL_RWSL_MASK)|SET(FLASH_CTL_RWSC(3u)),                   \
/* PRAMC0_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLOCK_PRAMC_PRCR1_FT_DIS,           \
/* PRAMC1_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLOCK_PRAMC_PRCR1_FT_DIS,           \
/* PRAMC2_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLOCK_PRAMC_PRCR1_FT_DIS,           \
/* CONFIG_REG_GPR   */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_APP_CORE_ACC(5u))|             \
/* ...              */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_FIRC_DIV_SEL(3u)),             \
/* FXOSC_CTRL       */ CLR(FXOSC_CTRL_OSC_BYP_MASK)|SET(FXOSC_CTRL_COMP_EN_MASK)|          \
/* ...              */ SET(FXOSC_CTRL_EOCV(157u))|SET(FXOSC_CTRL_GM_SEL(12u))|             \
/* ...              */ SET(FXOSC_CTRL_OSCON_MASK),                                         \
/* STDBY_ENABLE     */ SET(FIRC_STDBY_ENABLE_STDBY_EN_MASK),                               \
/* MISCELLANEOUS_IN */ SET(SIRC_MISCELLANEOUS_IN_STANDBY_ENABLE_MASK),                     \
/* PLLDV            */ SET(PLL_PLLDV_ODIV2(CLOCK_PLL_PLLDV_ODIV2))|                        \
/* ...              */ SET(PLL_PLLDV_RDIV(CLOCK_PLL_PLLDV_RDIV))|                          \
/* ...              */ SET(PLL_PLLDV_MFI(CLOCK_PLL_PLLDV_MFI)),                            \
/* PLLFD            */ CLR(PLL_PLLFD_SDMEN_MASK)|CLR(PLL_PLLFD_SDM2_MASK)|                 \
/* ...              */ CLR(PLL_PLLFD_SDM3_MASK)|CLR(PLL_PLLFD_MFN_MASK),                   \
/* PLLFM            */ SET(PLL_PLLFM_SSCGBYP_MASK)|CLR(PLL_PLLFM_SPREADCTL_MASK)|          \
/* ...              */ CLR(PLL_PLLFM_STEPSIZE_MASK)|CLR(PLL_PLLFM_STEPNO_MASK),            \
/* PLLODIV0         */ SET(PLL_PLLODIV_DIV(CLOCK_PLL_PLLODIV0_120)),                       \
/* PLLODIV1         */ SET(PLL_PLLODIV_DIV(CLOCK_PLL_PLLODIV1)),                           \
/* MUX_0_DC_0       */ SET(MC_CGM_MUX_0_DC_0_DIV(0u))|SET(MC_CGM_MUX_0_DC_0_DE_MASK),      \
/* MUX_0_DC_1       */ SET(MC_CGM_MUX_0_DC_1_DIV(1u))|SET(MC_CGM_MUX_0_DC_1_DE_MASK),      \
/* MUX_0_DC_2       */ SET(MC_CGM_MUX_0_DC_2_DIV(3u))|SET(MC_CGM_MUX_0_DC_2_DE_MASK),      \
/* MUX_0_DC_3       */ SET(MC_CGM_MUX_0_DC_3_DIV(0u))|SET(MC_CGM_MUX_0_DC_3_DE_MASK),      \
/* MUX_0_DC_4       */ SET(MC_CGM_MUX_0_DC_4_DIV(3u))|SET(MC_CGM_MUX_0_DC_4_DE_MASK),      \
/* MUX_0_CSC        */ SET(MC_CGM_MUX_0_CSC_SELCTL(8u))|SET(MC_CGM_MUX_0_CSC_CLK_SW_MASK)  \
}

/***************************************************************************//*!
 * @brief Configures device clocks.
 * @details Configures device clocks and memory wait states as shown below.
 *
 * Clock sources:
 * |Clock source  |Frequency in MHz |
 * |:------------:|:---------------:|
 * |FXOSC         |ON               |
 * |FIRC          |48               |
 * |PLL_VCO_CLK   |960              |
 * |PLL_ODIV2_CLK |240              |
 * |PLL_PHI0_CLK  |80               |
 * |PLL_PHI1_CLK  |48               |
 *
 * MC_CGM MUX0 output clocks:
 * |Clock         |Frequency in MHz |
 * |:------------:|:---------------:|
 * |CORE_CLK      |80               |
 * |AIPS_PLAT_CLK |80               |
 * |AIPS_SLOW_CLK |40               |
 * |HSE_CLK       |80               |
 * |DCM_CLK       |40               |
 * |LBIST_CLK     |40               |
 * |QSPI_MEM_CLK  |80               |
 *
 * Memory wait states:
 * |Memory       |Wait states |
 * |:-----------:|:----------:|
 * |Flash        |2           |
 * |SRAM (read)  |0           |
 *
 * @showinitializer
 ******************************************************************************/
#define CLOCK_MODE_2_CONFIG                                                               \
(tCLOCK_CONFIG){                                                                          \
/* FLASH_CTL        */ CLR(FLASH_CTL_RWSL_MASK)|SET(FLASH_CTL_RWSC(2u)),                  \
/* PRAMC0_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* PRAMC1_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* PRAMC2_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* CONFIG_REG_GPR   */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_APP_CORE_ACC(5u))|            \
/* ...              */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_FIRC_DIV_SEL(3u)),            \
/* FXOSC_CTRL       */ CLR(FXOSC_CTRL_OSC_BYP_MASK)|SET(FXOSC_CTRL_COMP_EN_MASK)|         \
/* ...              */ SET(FXOSC_CTRL_EOCV(157u))|SET(FXOSC_CTRL_GM_SEL(12u))|            \
/* ...              */ SET(FXOSC_CTRL_OSCON_MASK),                                        \
/* STDBY_ENABLE     */ SET(FIRC_STDBY_ENABLE_STDBY_EN_MASK),                              \
/* MISCELLANEOUS_IN */ SET(SIRC_MISCELLANEOUS_IN_STANDBY_ENABLE_MASK),                    \
/* PLLDV            */ SET(PLL_PLLDV_ODIV2(CLOCK_PLL_PLLDV_ODIV2))|                       \
/* ...              */ SET(PLL_PLLDV_RDIV(CLOCK_PLL_PLLDV_RDIV))|                         \
/* ...              */ SET(PLL_PLLDV_MFI(CLOCK_PLL_PLLDV_MFI)),                           \
/* PLLFD            */ CLR(PLL_PLLFD_SDMEN_MASK)|CLR(PLL_PLLFD_SDM2_MASK)|                \
/* ...              */ CLR(PLL_PLLFD_SDM3_MASK)|CLR(PLL_PLLFD_MFN_MASK),                  \
/* PLLFM            */ SET(PLL_PLLFM_SSCGBYP_MASK)|CLR(PLL_PLLFM_SPREADCTL_MASK)|         \
/* ...              */ CLR(PLL_PLLFM_STEPSIZE_MASK)|CLR(PLL_PLLFM_STEPNO_MASK),           \
/* PLLODIV0         */ SET(PLL_PLLODIV_DIV(CLOCK_PLL_PLLODIV0_80)),                       \
/* PLLODIV1         */ SET(PLL_PLLODIV_DIV(CLOCK_PLL_PLLODIV1)),                          \
/* MUX_0_DC_0       */ SET(MC_CGM_MUX_0_DC_0_DIV(0u))|SET(MC_CGM_MUX_0_DC_0_DE_MASK),     \
/* MUX_0_DC_1       */ SET(MC_CGM_MUX_0_DC_1_DIV(0u))|SET(MC_CGM_MUX_0_DC_1_DE_MASK),     \
/* MUX_0_DC_2       */ SET(MC_CGM_MUX_0_DC_2_DIV(1u))|SET(MC_CGM_MUX_0_DC_2_DE_MASK),     \
/* MUX_0_DC_3       */ SET(MC_CGM_MUX_0_DC_3_DIV(0u))|SET(MC_CGM_MUX_0_DC_3_DE_MASK),     \
/* MUX_0_DC_4       */ SET(MC_CGM_MUX_0_DC_4_DIV(1u))|SET(MC_CGM_MUX_0_DC_4_DE_MASK),     \
/* MUX_0_CSC        */ SET(MC_CGM_MUX_0_CSC_SELCTL(8u))|SET(MC_CGM_MUX_0_CSC_CLK_SW_MASK) \
}

#if(configXTAL_FREQ == 0)
#undef CLOCK_MODE_5_CONFIG
#undef CLOCK_MODE_4_CONFIG
#undef CLOCK_MODE_3_CONFIG
#undef CLOCK_MODE_2_CONFIG
#endif

/***************************************************************************//*!
 * @brief Configures device clocks.
 * @details Configures device clocks and memory wait states as shown below:
 *
 * Clock sources:
 * |Clock source  |Frequency in MHz |
 * |:------------:|:---------------:|
 * |FXOSC         |OFF              |
 * |FIRC          |48               |
 * |PLL_VCO_CLK   |OFF              |
 * |PLL_ODIV2_CLK |OFF              |
 * |PLL_PHI0_CLK  |OFF              |
 * |PLL_PHI1_CLK  |OFF              |
 *
 * MC_CGM MUX0 output clocks:
 * |Clock         |Frequency in MHz |
 * |:------------:|:---------------:|
 * |CORE_CLK      |48               |
 * |AIPS_PLAT_CLK |48               |
 * |AIPS_SLOW_CLK |24               |
 * |HSE_CLK       |48               |
 * |DCM_CLK       |48               |
 * |LBIST_CLK     |48               |
 * |QSPI_MEM_CLK  |48               |
 *
 * Memory wait states:
 * |Memory       |Wait states |
 * |:-----------:|:----------:|
 * |Flash        |1           |
 * |SRAM (read)  |0           |
 *
 * @showinitializer
 ******************************************************************************/
#define CLOCK_MODE_1_CONFIG                                                               \
(tCLOCK_CONFIG){                                                                          \
/* FLASH_CTL        */ CLR(FLASH_CTL_RWSL_MASK)|SET(FLASH_CTL_RWSC(1u)),                  \
/* PRAMC0_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* PRAMC1_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* PRAMC2_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* CONFIG_REG_GPR   */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_APP_CORE_ACC(5u))|            \
/* ...              */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_FIRC_DIV_SEL(3u)),            \
/* FXOSC_CTRL       */ 0x00000000ul,                                                      \
/* STDBY_ENABLE     */ SET(FIRC_STDBY_ENABLE_STDBY_EN_MASK),                              \
/* MISCELLANEOUS_IN */ SET(SIRC_MISCELLANEOUS_IN_STANDBY_ENABLE_MASK),                    \
/* PLLDV            */ 0x00000000ul,                                                      \
/* PLLFD            */ 0x00000000ul,                                                      \
/* PLLFM            */ 0x00000000ul,                                                      \
/* PLLODIV0         */ 0x00000000ul,                                                      \
/* PLLODIV1         */ 0x00000000ul,                                                      \
/* MUX_0_DC_0       */ SET(MC_CGM_MUX_0_DC_0_DIV(0u))|SET(MC_CGM_MUX_0_DC_0_DE_MASK),     \
/* MUX_0_DC_1       */ SET(MC_CGM_MUX_0_DC_1_DIV(0u))|SET(MC_CGM_MUX_0_DC_1_DE_MASK),     \
/* MUX_0_DC_2       */ SET(MC_CGM_MUX_0_DC_2_DIV(1u))|SET(MC_CGM_MUX_0_DC_2_DE_MASK),     \
/* MUX_0_DC_3       */ SET(MC_CGM_MUX_0_DC_3_DIV(0u))|SET(MC_CGM_MUX_0_DC_3_DE_MASK),     \
/* MUX_0_DC_4       */ SET(MC_CGM_MUX_0_DC_4_DIV(0u))|SET(MC_CGM_MUX_0_DC_4_DE_MASK),     \
/* MUX_0_CSC        */ SET(MC_CGM_MUX_0_CSC_SELCTL(0u))|SET(MC_CGM_MUX_0_CSC_CLK_SW_MASK) \
}

/***************************************************************************//*!
 * @brief Configures device clocks.
 * @details Configures device clocks and memory wait states as shown below:
 *
 * Clock sources:
 * |Clock source  |Frequency in MHz |
 * |:------------:|:---------------:|
 * |FXOSC         |OFF              |
 * |FIRC          |24               |
 * |PLL_VCO_CLK   |OFF              |
 * |PLL_ODIV2_CLK |OFF              |
 * |PLL_PHI0_CLK  |OFF              |
 * |PLL_PHI1_CLK  |OFF              |
 *
 * MC_CGM MUX0 output clocks:
 * |Clock         |Frequency in MHz |
 * |:------------:|:---------------:|
 * |CORE_CLK      |24               |
 * |AIPS_PLAT_CLK |24               |
 * |AIPS_SLOW_CLK |12               |
 * |HSE_CLK       |24               |
 * |DCM_CLK       |24               |
 * |LBIST_CLK     |24               |
 * |QSPI_MEM_CLK  |24               |
 *
 * Memory wait states:
 * |Memory       |Wait states |
 * |:-----------:|:----------:|
 * |Flash        |1           |
 * |SRAM (read)  |0           |
 *
 * @showinitializer
 ******************************************************************************/
#define CLOCK_MODE_0_CONFIG                                                               \
(tCLOCK_CONFIG){                                                                          \
/* FLASH_CTL        */ CLR(FLASH_CTL_RWSL_MASK)|SET(FLASH_CTL_RWSC(1u)),                  \
/* PRAMC0_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* PRAMC1_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* PRAMC2_PRCR1     */ CLR(PRAMC_PRCR1_P0_BO_DIS_MASK)|CLR(PRAMC_PRCR1_FT_DIS_MASK),      \
/* CONFIG_REG_GPR   */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_APP_CORE_ACC(5u))|            \
/* ...              */ SET(CONFIGURATION_GPR_CONFIG_REG_GPR_FIRC_DIV_SEL(0u)),            \
/* FXOSC_CTRL       */ 0x00000000ul,                                                      \
/* STDBY_ENABLE     */ SET(FIRC_STDBY_ENABLE_STDBY_EN_MASK),                              \
/* MISCELLANEOUS_IN */ SET(SIRC_MISCELLANEOUS_IN_STANDBY_ENABLE_MASK),                    \
/* PLLDV            */ 0x00000000ul,                                                      \
/* PLLFD            */ 0x00000000ul,                                                      \
/* PLLFM            */ 0x00000000ul,                                                      \
/* PLLODIV0         */ 0x00000000ul,                                                      \
/* PLLODIV1         */ 0x00000000ul,                                                      \
/* MUX_0_DC_0       */ SET(MC_CGM_MUX_0_DC_0_DIV(0u))|SET(MC_CGM_MUX_0_DC_0_DE_MASK),     \
/* MUX_0_DC_1       */ SET(MC_CGM_MUX_0_DC_1_DIV(0u))|SET(MC_CGM_MUX_0_DC_1_DE_MASK),     \
/* MUX_0_DC_2       */ SET(MC_CGM_MUX_0_DC_2_DIV(1u))|SET(MC_CGM_MUX_0_DC_2_DE_MASK),     \
/* MUX_0_DC_3       */ SET(MC_CGM_MUX_0_DC_3_DIV(0u))|SET(MC_CGM_MUX_0_DC_3_DE_MASK),     \
/* MUX_0_DC_4       */ SET(MC_CGM_MUX_0_DC_4_DIV(0u))|SET(MC_CGM_MUX_0_DC_4_DE_MASK),     \
/* MUX_0_CSC        */ SET(MC_CGM_MUX_0_CSC_SELCTL(0u))|SET(MC_CGM_MUX_0_CSC_CLK_SW_MASK) \
}
/*! @} End of clock_config                                                    */

/******************************************************************************
* MC_MCG clock multiplexer selection
*
*//*! @addtogroup clock_cgm_mux
* @{
*******************************************************************************/
#define CLOCK_MUX1                  1       ///< Mux 1
#define CLOCK_MUX2                  2       ///< Mux 2
#define CLOCK_MUX3                  3       ///< Mux 3
#define CLOCK_MUX4                  4       ///< Mux 4
#define CLOCK_MUX7                  7       ///< Mux 7
#define CLOCK_MUX8                  8       ///< Mux 8
#define CLOCK_MUX9                  9       ///< Mux 9
#define CLOCK_MUX10                 10      ///< Mux 10
/*! @} End of clock_cgm_mux                                                   */

/******************************************************************************
* MC_MCG clock sources
*
*//*! @addtogroup clock_cgm_clk
* @{
*******************************************************************************/
#define CLOCK_FIRC_CLK              0u      ///< FIRC clock
#define CLOCK_SIRC_CLK              1u      ///< SIRC clock
#define CLOCK_FXOSC_CLK             2u      ///< FXOSC clock
#define CLOCK_SXOSC_CLK             4u      ///< SXOSC clock
#define CLOCK_PLL_PHI0_CLK          8u      ///< PLL PHI0 clock
#define CLOCK_PLL_PHI1_CLK          9u      ///< PLL PHI1 clock
#define CLOCK_CORE_CLK              16u     ///< M7 core clock
#define CLOCK_HSE_CLK               19u     ///< HSE clock
#define CLOCK_AIPS_PLAT_CLK         22u     ///< SRAM/AXBS clock
#define CLOCK_AIPS_SLOW_CLK         23u     ///< peripheral clock
#define CLOCK_EMAC_MII_RMII_TX_CLK  24u     ///< Ethernet MAC MII/RMII transmit clock
#define CLOCK_CLKOUT_RUN_CLK        24u     ///< Clock output in RUN mode
#define CLOCK_EMAC_RX_CLK           25u     ///< Ethernet MAC Receive clock
/*! @} End of clock_cgm_clk                                                   */

/******************************************************************************
* MC_MCG CLKOUT clock output selection
*
*//*! @addtogroup clock_cgm_clkout
* @{
*******************************************************************************/
#define CLOCK_CLKOUT_STBY           5       ///< Clock output in Standby mode
#define CLOCK_CLKOUT_RUN            6       ///< Clock output in RUN mode
/*! @} End of clock_cgm_clkout                                                */

/******************************************************************************
* FIRC divider selection
*
*//*! @addtogroup clock_firc_div
* @{
*******************************************************************************/
#define CLOCK_FIRC_DIV2             0u      ///< FIRC clock divided by 2
#define CLOCK_FIRC_DIV16            2u      ///< FIRC clock divided by 16
#define CLOCK_FIRC_DIVBYPASS        3u      ///< FIRC divider bypassed
/*! @} End of clock_firc_div                                                  */

/******************************************************************************
* Clock related function and macro definitions
*
*//*! @addtogroup clock_macro
* @{
*******************************************************************************/
#define CLOCK_MuxInit_(mux, src, div)                                                              \
do{                                                                                                \
  while((MC_CGM->MUX_##mux##_CSS & MC_CGM_MUX_##mux##_CSS_SWIP_MASK) != 0)                         \
  {                                                                                                \
  }                                                                                                \
  if(div == 0)                                                                                     \
  {                                                                                                \
    MC_CGM->MUX_##mux##_DC_0 = 0ul;                                                                \
  }                                                                                                \
  else                                                                                             \
  {                                                                                                \
    MC_CGM->MUX_##mux##_CSC = MC_CGM_MUX_##mux##_CSC_SELCTL(src);                                  \
    MC_CGM->MUX_##mux##_DC_0 = MC_CGM_MUX_##mux##_DC_0_DIV(div - 1);                               \
    MC_CGM->MUX_##mux##_DC_0 |= MC_CGM_MUX_##mux##_DC_0_DE_MASK;                                   \
    while((MC_CGM->MUX_##mux##_DIV_UPD_STAT & MC_CGM_MUX_##mux##_DIV_UPD_STAT_DIV_STAT_MASK) != 0) \
    {                                                                                              \
    }                                                                                              \
    MC_CGM->MUX_##mux##_CSC |= MC_CGM_MUX_##mux##_CSC_CLK_SW_MASK;                                 \
    while((MC_CGM->MUX_##mux##_CSS & MC_CGM_MUX_##mux##_CSS_CLK_SW_MASK) == 0)                     \
    {                                                                                              \
    }                                                                                              \
    while((MC_CGM->MUX_##mux##_CSS & MC_CGM_MUX_1_CSS_SWIP_MASK) != 0)                             \
    {                                                                                              \
    }                                                                                              \
  }                                                                                                \
}while(0)
/***************************************************************************//*!
 * @brief   Configures selected MC_CGM clock multiplexer and related divider.
 * @details This macro configures selected MC_CGM clock multiplexer and related
 *          divider (except of muxes 0, 5, 6, and 11).
 * @param   mux       One of @ref clock_cgm_mux.
 * @param   src       See @ref clock_cgm_clk for valid multiplexer clock source.
 * @param   div       See @ref clock_cgm_mux for valid divider division range.
 *                    To disable selected MC_CGM multiplexer clock divider, set
 *                    div value to 0.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLOCK_MuxInit(mux, src, div)                                           \
CLOCK_MuxInit_(mux, src, div)

#define CLOCK_GetMuxClkSwStatus_(mux)                                          \
(tCLOCK_SW_STATUS)((MC_CGM->MUX_##mux##_CSS & MC_CGM_MUX_##mux##_CSS_SWTRG_MASK) >> MC_CGM_MUX_##mux##_CSS_SWTRG_SHIFT)
/***************************************************************************//*!
 * @brief   Returns selected MC_CGM clock multiplexer clock switch status.
 * @details This macro returns selected MC_CGM clock multiplexer clock switch
 *          status (except of muxes 0, 5, 6, and 11). It validates that the
 *          multiplexer clock was successfully switched to a target clock after
 *          @ref CLOCK_MuxInit function call.
 * @param   mux       One of @ref clock_cgm_mux.
 * @return  @ref tCLOCK_SW_STATUS
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLOCK_GetMuxClkSwStatus(mux)                                           \
CLOCK_GetMuxClkSwStatus_(mux)

#define CLOCK_ClkoutInit_(clkout, src, div)                                                     \
do{                                                                                             \
  if(div == 0)                                                                                  \
  {                                                                                             \
    MC_CGM->MUX_##clkout##_CSC = MC_CGM_MUX_##clkout##_CSC_CG_MASK;                             \
    MC_CGM->MUX_##clkout##_DC_0 = 0ul;                                                          \
  }                                                                                             \
  else                                                                                          \
  {                                                                                             \
    MC_CGM->MUX_##clkout##_CSC = MC_CGM_MUX_##clkout##_CSC_SELCTL(src);                         \
    MC_CGM->MUX_##clkout##_DC_0 = MC_CGM_MUX_##clkout##_DC_0_DIV(div - 1);                      \
    MC_CGM->MUX_##clkout##_DC_0 |= MC_CGM_MUX_##clkout##_DC_0_DE_MASK;                          \
    while((MC_CGM->MUX_##clkout##_DIV_UPD_STAT & MC_CGM_MUX_0_DIV_UPD_STAT_DIV_STAT_MASK) != 0) \
    {                                                                                           \
    }                                                                                           \
  }                                                                                             \
}while(0)
/***************************************************************************//*!
 * @brief   Configures selected MC_CGM CLKOUT clock output.
 * @details This macro configures selected MC_CGM CLKOUT clock output.
 * @param   clkout    One of @ref clock_cgm_clkout.
 * @param   src       See MUX5 (CLKOUT_STANDBY) and MUX6 (CLKOUT_RUN) input
 *                    clock options in @ref clock_cgm_clk.
 * @param   div       See @ref clock_cgm_mux for valid divider division range.
 *                    To disable selected MC_CGM CLKOUT multiplexer clock
 *                    divider and enable clock gating, set div value to 0.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLOCK_ClkoutInit(clkout, src, div)                                     \
CLOCK_ClkoutInit_(clkout, src, div)

/***************************************************************************//*!
 * @brief   Configures selected MC_CGM TRACE_CLK clock output.
 * @details This macro configures MC_CGM TRACE_CLK clock output.
 * @param   src       See MUX11 (TRACE_CLK) input clock options in @ref
 *                    clock_cgm_clk.
 * @param   div       See @ref clock_cgm_mux for valid divider division range.
 *                    To disable MC_CGM TRACE_CLK clock divider and enable clock
 *                    gating, set div value to 0.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLOCK_TraceClkInit(src, div)                                                    \
do{                                                                                     \
  MC_CGM->MUX_11_CSC = MC_CGM_MUX_11_CSC_SELCTL(src);                                   \
  if(div == 0)                                                                          \
  {                                                                                     \
    MC_CGM->MUX_11_CSC = MC_CGM_MUX_11_CSC_CG_MASK;                                     \
    MC_CGM->MUX_11_DC_0 = 0ul;                                                          \
  }                                                                                     \
  else                                                                                  \
  {                                                                                     \
    MC_CGM->MUX_11_DC_0 = MC_CGM_MUX_11_DC_0_DIV(div - 1);                              \
    MC_CGM->MUX_11_DC_0 |= MC_CGM_MUX_11_DC_0_DE_MASK;                                  \
    while((MC_CGM->MUX_11_DIV_UPD_STAT & MC_CGM_MUX_0_DIV_UPD_STAT_DIV_STAT_MASK) != 0) \
    {                                                                                   \
    }                                                                                   \
  }                                                                                     \
}while(0)

/***************************************************************************//*!
 * @brief   Configures FIRC output divider.
 * @details This macro configures Fast Internal RC Oscillator (FIRC) output
 *          divider.
 * @param   div       One of @ref clock_firc_div.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLOCK_SetFIRCDivider(div)                                                                       \
do{                                                                                                     \
  *(uint32_t *)&CONFIGURATION_GPR->CONFIG_REG_GPR = CONFIGURATION_GPR_CONFIG_REG_GPR_APP_CORE_ACC(5u) | \
                                                    CONFIGURATION_GPR_CONFIG_REG_GPR_FIRC_DIV_SEL(div)  \
}while(0);

/***************************************************************************//*!
 * @brief   Enables SXOSC oscillator.
 * @details This macro enables Slow Crystal Oscillator (SXOSC).
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLOCK_EnableSXOSC()                                                       \
do{                                                                               \
  if((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK51_MASK) == 0u)       \
  {                                                                               \
    MC_ME->PRTN1_COFB1_CLKEN |= MC_ME_PRTN1_COFB1_CLKEN_REQ51_MASK;               \
    MC_ME->PRTN1_PCONF = MC_ME_PRTN1_PCONF_PCE_MASK;                              \
    MC_ME->PRTN1_PUPD = MC_ME_PRTN1_PUPD_PCUD_MASK;                               \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(0x5AF0);                                   \
    MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);                                  \
    while ((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK51_MASK) == 0u) \
    {                                                                             \
    }                                                                             \
  }                                                                               \
                                                                                  \
  SXOSC->SXOSC_CTRL = SXOSC_SXOSC_CTRL_EOCV(125) | SXOSC_SXOSC_CTRL_OSCON_MASK;   \
  while((SXOSC->SXOSC_STAT & SXOSC_SXOSC_STAT_OSC_STAT_MASK) == 0u)               \
  {                                                                               \
  }                                                                               \
}while(0)

/***************************************************************************//*!
 * @brief   Enables SXOSC oscillator.
 * @details This macro enables Slow Crystal Oscillator (SXOSC).
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLOCK_DisableSXOSC()                                                   \
do{                                                                            \
  if((SXOSC->SXOSC_STAT & SXOSC_SXOSC_STAT_OSC_STAT_MASK) != 0u)               \
  {                                                                            \
    SXOSC->SXOSC_CTRL = 0x00000000;                                            \
  }                                                                            \
}while(0)

/******************************************************************************
 * public function prototypes                                                 *
 ******************************************************************************/
/***************************************************************************//*!
 * @brief   Clock initialization.
 * @details This function configures Flash and SRAM memory wait states, FIRC
 *          divider, FXOSC and SXOSC availability in both RUN and STANDBY
 *          modes, PLL, and MC_CGM multiplexer 0 clock source and dividers.
 *          <br><br>
 *          This function is called automatically after system startup with a
 *          cfg input parameter value derived from configCLOCK_MODE macro value
 *          defined in appconfig.h (CLOCK_MODE_<configCLOCK_MODE>_CONFIG). See
 *          @ref project_config for more information.
 * @param   cfg      One of @ref clock_config.
 * @note    Implemented as a function call.
 ******************************************************************************/
void CLOCK_Init(tCLOCK_CONFIG cfg);
/*! @} End of clock_macro                                                     */

#endif /* __CLOCK_H */
