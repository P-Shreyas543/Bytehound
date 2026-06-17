/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      siul.c
 * @brief     System Integration Unit Lite2 (SIUL) driver source code.
 */
#include "common.h"
#include "siul.h"

/******************************************************************************
 * private Virtual SIUL base address definitions                              *
 ******************************************************************************/
volatile SIUL2_Type * const prvVSIUL[] = 
{
  (SIUL2_Type *)0x40290000UL, 
  (SIUL2_Type *)0x40298000UL, 
  (SIUL2_Type *)0x402A0000UL
};

/******************************************************************************
 * data type definitions                                                      *
 ******************************************************************************/
static const IRQn_Type siul_irqs[] = {SIUL_0_IRQn, SIUL_1_IRQn, SIUL_2_IRQn, SIUL_3_IRQn};
static uint16_t slot_num = 0U;
static tSIUL_CALLBACK pCallbackSIUL[4];

/******************************************************************************
 * public function definitions                                                *
 ******************************************************************************/
void VSIUL_prvInstallCallback (uint16_t slot, uint8_t vector, uint8_t ip, tSIUL_CALLBACK pCallback)
{
  slot_num = slot;
  pCallbackSIUL[vector] = pCallback;
  NVIC_SetPriority (siul_irqs[vector], ip);
  NVIC_EnableIRQ (siul_irqs[vector]);
}

/******************************************************************************
 * interrupt function definitions                                             *
 ******************************************************************************/
__WEAK __HANDLERFUNC void SIUL_0_Handler(void)
{
  register uint32_t tmp = prvVSIUL[slot_num]->DISR0 & 0x000000FFU;
  tmp &= ~prvVSIUL[slot_num]->DIRSR0;
  tmp &=  prvVSIUL[slot_num]->DIRER0;
  if(tmp) 
  { 
    pCallbackSIUL[0]((tSIUL_CALLBACK_TYPE)(prvVSIUL[slot_num]->DISR0 = tmp)); 
  }
}

__WEAK __HANDLERFUNC void SIUL_1_Handler(void)
{
  register uint32_t tmp = prvVSIUL[slot_num]->DISR0 & 0x0000FF00U;
  tmp &= ~prvVSIUL[slot_num]->DIRSR0;
  tmp &=  prvVSIUL[slot_num]->DIRER0;
  if(tmp) 
  { 
    pCallbackSIUL[1]((tSIUL_CALLBACK_TYPE)(prvVSIUL[slot_num]->DISR0 = tmp)); 
  }
}

__WEAK __HANDLERFUNC void SIUL_2_Handler(void)
{
  register uint32_t tmp = prvVSIUL[slot_num]->DISR0 & 0x00FF0000U;
  tmp &= ~prvVSIUL[slot_num]->DIRSR0;
  tmp &=  prvVSIUL[slot_num]->DIRER0;
  if(tmp) 
  { 
    pCallbackSIUL[2]((tSIUL_CALLBACK_TYPE)(prvVSIUL[slot_num]->DISR0 = tmp)); 
  }
}

__WEAK __HANDLERFUNC void SIUL_3_Handler(void)
{
  register uint32_t tmp = prvVSIUL[slot_num]->DISR0 & 0xFF000000U;
  tmp &= ~prvVSIUL[slot_num]->DIRSR0;
  tmp &=  prvVSIUL[slot_num]->DIRER0;
  if(tmp)
  { 
    pCallbackSIUL[3]((tSIUL_CALLBACK_TYPE)(prvVSIUL[slot_num]->DISR0 = tmp)); 
  }
}
/******************************************************************************
 * End of module                                                              *
 ******************************************************************************/
