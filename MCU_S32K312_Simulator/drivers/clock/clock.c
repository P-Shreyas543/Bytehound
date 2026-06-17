/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      clock.c
 * @brief     Clock Generation Module (MC_CGM), Fast Internal RC Oscillator
 *            (FIRC), Slow Internal RC Oscillator (SIRC), Fast Crystal
 *            Oscillator Digital Controller (FIRC), Slow Crystal Oscillator
 *            Digital Controller (SIRC), and PLL Digital Interface (PLLDIG)
 *            driver source code.
 */
#include "common.h"
#include "clock.h"

__tcmfunc static void CLOCK_prvWriteFlashCTL(uint32_t flash_ctl)
{
  __DSB();
  __ISB();
  FLASH->CTL = flash_ctl;
}

void CLOCK_Init(tCLOCK_CONFIG cfg)
{
  /* Configure MC_CGM_MUX0 to run from FIRC clock to allow PLL reconfig.      */
  MC_CGM->MUX_0_DIV_TRIG_CTRL = MC_CGM_MUX_0_DIV_TRIG_CTRL_TCTL_MASK | \
                                MC_CGM_MUX_0_DIV_TRIG_CTRL_HHEN_MASK;
  MC_CGM->MUX_0_DC_0 = MC_CGM_MUX_0_DC_0_DIV(0u) | MC_CGM_MUX_0_DC_0_DE_MASK;
  MC_CGM->MUX_0_DC_1 = MC_CGM_MUX_0_DC_1_DIV(0u) | MC_CGM_MUX_0_DC_1_DE_MASK;
  MC_CGM->MUX_0_DC_2 = MC_CGM_MUX_0_DC_2_DIV(1u) | MC_CGM_MUX_0_DC_2_DE_MASK;
  MC_CGM->MUX_0_DC_3 = MC_CGM_MUX_0_DC_3_DIV(0u) | MC_CGM_MUX_0_DC_3_DE_MASK;
  MC_CGM->MUX_0_DC_4 = MC_CGM_MUX_0_DC_4_DIV(0u) | MC_CGM_MUX_0_DC_4_DE_MASK;
  MC_CGM->MUX_0_DIV_TRIG = MC_CGM_MUX_0_DIV_TRIG_TRIGGER(1u);
  /* Trigger clock transition for MC_CGM_MUX0                                 */
  while((MC_CGM->MUX_0_DIV_UPD_STAT & MC_CGM_MUX_0_DIV_UPD_STAT_DIV_STAT_MASK) != 0)
  {
  }
  while((MC_CGM->MUX_0_CSS & MC_CGM_MUX_0_CSS_SWIP_MASK) != 0)
  {
  }
  MC_CGM->MUX_0_CSC = MC_CGM_MUX_0_CSC_SELCTL(0u) | MC_CGM_MUX_0_CSC_CLK_SW_MASK;
  while((MC_CGM->MUX_0_CSS & MC_CGM_MUX_0_CSS_CLK_SW_MASK) == 0)
  {
  }

  /* Set 1 flash wait state                                                   */
  CLOCK_prvWriteFlashCTL(FLASH_CTL_RWSC(1u));

  /* Set SRAM to 0 read wait states                                           */
  PRAMC_0->PRCR1 = 0x0ul;

  /* Configure FIRC output divider                                            */
  /* *(uint32_t *)&CONFIGURATION_GPR->CONFIG_REG_GPR = cfg.CONFIG_REG_GPR; => Causes hard fault on E5 samples run mode with debugger disconnected */

  /* Configure FXOSC                                                          */
  if(cfg.FXOSC_CTRL == 0ul)
  {
    if((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK53_MASK) != 0u)
    {
      /* Disable FXOSC                                                        */
      FXOSC->CTRL = 0x0ul;
    }
  }
  else
  {
    if((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK53_MASK) == 0u)
    {
      /* Enable FXOSC peripheral clock                                        */
      MC_ME->PRTN1_COFB1_CLKEN |= MC_ME_PRTN1_COFB1_CLKEN_REQ53_MASK;
      MC_ME->PRTN1_PCONF = MC_ME_PRTN1_PCONF_PCE_MASK;
      MC_ME->PRTN1_PUPD = MC_ME_PRTN1_PUPD_PCUD_MASK;
      MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(0x5AF0);
      MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);
      while ((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK53_MASK) == 0u)
      {
      }
    }

    /* Enable FXOSC                                                           */
    FXOSC->CTRL = cfg.FXOSC_CTRL;
    while((FXOSC->STAT & FXOSC_STAT_OSC_STAT_MASK) == 0u)
    {
    }
  }

  /* Configure PLL                                                            */
  if(cfg.PLLDV == 0ul)
  {
    if((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK56_MASK) != 0u)
    {
      /* Disable PLL                                                          */
      PLL->PLLCR = PLL_PLLCR_PLLPD_MASK;
    }
  }
  else
  {
    if((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK56_MASK) == 0u)
    {
      /* Enable PLLDIG peripheral clock                                       */
      MC_ME->PRTN1_COFB1_CLKEN |= MC_ME_PRTN1_COFB1_CLKEN_REQ56_MASK;
      MC_ME->PRTN1_PCONF = MC_ME_PRTN1_PCONF_PCE_MASK;
      MC_ME->PRTN1_PUPD = MC_ME_PRTN1_PUPD_PCUD_MASK;
      MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(0x5AF0);
      MC_ME->CTL_KEY = MC_ME_CTL_KEY_KEY(~0x5AF0);
      while ((MC_ME->PRTN1_COFB1_STAT & MC_ME_PRTN1_COFB1_STAT_BLOCK56_MASK) == 0u)
      {
      }
    }

    PLL->PLLODIV[0] = (uint32_t)0ul;
    PLL->PLLODIV[1] = (uint32_t)0ul;
    PLL->PLLCR = PLL_PLLCR_PLLPD_MASK;
    PLL->PLLDV = cfg.PLLDV;
    PLL->PLLFD = cfg.PLLFD;
    PLL->PLLODIV[0] |= cfg.PLLODIV0;
    PLL->PLLODIV[1] |= cfg.PLLODIV1;
    /* Enable PLL                                                             */
    PLL->PLLCR = (uint32_t)0ul;
    while((PLL->PLLSR & PLL_PLLSR_LOCK_MASK) == 0u)
    {
    }
    PLL->PLLODIV[0] |= PLL_PLLODIV_DE_MASK;
    PLL->PLLODIV[1] |= PLL_PLLODIV_DE_MASK;
  }

  MC_CGM->MUX_0_DIV_TRIG_CTRL = MC_CGM_MUX_0_DIV_TRIG_CTRL_TCTL_MASK | \
                                MC_CGM_MUX_0_DIV_TRIG_CTRL_HHEN_MASK;
  MC_CGM->MUX_0_DC_0 = cfg.MUX_0_DC_0;
  MC_CGM->MUX_0_DC_1 = cfg.MUX_0_DC_1;
  MC_CGM->MUX_0_DC_2 = cfg.MUX_0_DC_2;
  MC_CGM->MUX_0_DC_3 = cfg.MUX_0_DC_3;
  MC_CGM->MUX_0_DC_4 = cfg.MUX_0_DC_4;

  /* Configure flash wait states                                              */
  CLOCK_prvWriteFlashCTL(cfg.CTL);

  /* Configure SRAM read wait states                                          */
  PRAMC_0->PRCR1 = cfg.PRAMC0_PRCR1;

  /* Trigger clock transition for MC_CGM_MUX0                                 */
  MC_CGM->MUX_0_DIV_TRIG = MC_CGM_MUX_0_DIV_TRIG_TRIGGER(1u);
  while((MC_CGM->MUX_0_DIV_UPD_STAT & MC_CGM_MUX_0_DIV_UPD_STAT_DIV_STAT_MASK) != 0)
  {
  }
  while((MC_CGM->MUX_0_CSS & MC_CGM_MUX_0_CSS_SWIP_MASK) != 0)
  {
  }
  MC_CGM->MUX_0_CSC = cfg.MUX_0_CSC;
  while((MC_CGM->MUX_0_CSS & MC_CGM_MUX_0_CSS_CLK_SW_MASK) == 0)
  {
  }

  /* Configure FIRC behavior in STANDBY mode                                  */
  FIRC->STDBY_ENABLE = cfg.STDBY_ENABLE;

  /* Configure SIRC behavior in STANDBY mode                                  */
  SIRC->MISCELLANEOUS_IN = cfg.MISCELLANEOUS_IN;
}
/******************************************************************************
 * End of module                                                              *
 ******************************************************************************/
