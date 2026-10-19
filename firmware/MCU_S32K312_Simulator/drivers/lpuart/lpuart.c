/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      lpuart.c
 * @brief     Low Power Universal Asynchronous Receiver/Transmitter (LPUART) driver source code.
 */
#include "common.h"
#include "lpuart.h"

/******************************************************************************
 * data type definitions                                                      *
 ******************************************************************************/
static tLPUART_CALLBACK pCallbackLPUART[LPUART_INSTANCE_COUNT];

/******************************************************************************
 * public function definitions                                                *
 ******************************************************************************/
void LPUART_prvInit (volatile LPUART_Type *module, tLPUART cfg)
{
  /* Disable LPUART operation                                                 */
  module->CTRL &= ~(LPUART_CTRL_TE_MASK | LPUART_CTRL_RE_MASK );

  module->PINCFG = cfg.PINCFG; /* Pin Configuration Register */
  module->BAUD = cfg.BAUD; /* Baud Rate Register */
  module->STAT = cfg.STAT; /* Status Register */
  module->CTRL = cfg.CTRL; /* Control Register */
  module->MODIR = cfg.MODIR; /* Modem IrDA Register */
}

void LPUART0_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[0] = pCallback;
  NVIC_SetPriority (LPUART0_IRQn, ip);
  NVIC_EnableIRQ (LPUART0_IRQn);
}

#if defined(LPUART1)
void LPUART1_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[1] = pCallback;
  NVIC_SetPriority (LPUART1_IRQn, ip);
  NVIC_EnableIRQ (LPUART1_IRQn);
}
#endif

#if defined(LPUART2)
void LPUART2_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[2] = pCallback;
  NVIC_SetPriority (LPUART2_IRQn, ip);
  NVIC_EnableIRQ (LPUART2_IRQn);
}
#endif

#if defined(LPUART3)
void LPUART3_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[3] = pCallback;
  NVIC_SetPriority (LPUART3_IRQn, ip);
  NVIC_EnableIRQ (LPUART3_IRQn);
}
#endif

#if defined(LPUART4)
void LPUART4_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[4] = pCallback;
  NVIC_SetPriority (LPUART4_IRQn, ip);
  NVIC_EnableIRQ (LPUART4_IRQn);
}
#endif

#if defined(LPUART5)
void LPUART5_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[5] = pCallback;
  NVIC_SetPriority (LPUART5_IRQn, ip);
  NVIC_EnableIRQ (LPUART5_IRQn);
}
#endif

#if defined(LPUART6)
void LPUART6_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[6] = pCallback;
  NVIC_SetPriority (LPUART6_IRQn, ip);
  NVIC_EnableIRQ (LPUART6_IRQn);
}
#endif

#if defined(LPUART7)
void LPUART7_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[7] = pCallback;
  NVIC_SetPriority (LPUART7_IRQn, ip);
  NVIC_EnableIRQ (LPUART7_IRQn);
}
#endif

#if defined(LPUART8)
void LPUART8_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[8] = pCallback;
  NVIC_SetPriority (LPUART8_IRQn, ip);
  NVIC_EnableIRQ (LPUART8_IRQn);
}
#endif

#if defined(LPUART9)
void LPUART9_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[9] = pCallback;
  NVIC_SetPriority (LPUART9_IRQn, ip);
  NVIC_EnableIRQ (LPUART9_IRQn);
}
#endif

#if defined(LPUART10)
void LPUART10_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[10] = pCallback;
  NVIC_SetPriority (LPUART10_IRQn, ip);
  NVIC_EnableIRQ (LPUART10_IRQn);
}
#endif

#if defined(LPUART11)
void LPUART11_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[11] = pCallback;
  NVIC_SetPriority (LPUART11_IRQn, ip);
  NVIC_EnableIRQ (LPUART11_IRQn);
}
#endif

#if defined(LPUART12)
void LPUART12_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[12] = pCallback;
  NVIC_SetPriority (LPUART12_IRQn, ip);
  NVIC_EnableIRQ (LPUART12_IRQn);
}
#endif

#if defined(LPUART13)
void LPUART13_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[13] = pCallback;
  NVIC_SetPriority (LPUART13_IRQn, ip);
  NVIC_EnableIRQ (LPUART13_IRQn);
}
#endif

#if defined(LPUART14)
void LPUART14_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[14] = pCallback;
  NVIC_SetPriority (LPUART14_IRQn, ip);
  NVIC_EnableIRQ (LPUART14_IRQn);
}
#endif

#if defined(LPUART15)
void LPUART15_InstallCallback (uint8_t ip, tLPUART_CALLBACK pCallback)
{
  pCallbackLPUART[15] = pCallback;
  NVIC_SetPriority (LPUART15_IRQn, ip);
  NVIC_EnableIRQ (LPUART15_IRQn);
}
#endif

/******************************************************************************
 * interrupt function definitions                                             *
 ******************************************************************************/
__HANDLERFUNC void LPUART0_Handler(void)
{ 
  pCallbackLPUART[0](LPUART0, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART0)); 
}
#if defined(LPUART1)
__HANDLERFUNC void LPUART1_Handler(void)
{ 
  pCallbackLPUART[1](LPUART1, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART1)); }
#endif
#if defined(LPUART2)
__HANDLERFUNC void LPUART2_Handler(void)
{ 
  pCallbackLPUART[2](LPUART2, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART2));
}
#endif
#if defined(LPUART3)
__HANDLERFUNC void LPUART3_Handler(void)
{ 
  pCallbackLPUART[3](LPUART3, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART3)); 
}
#endif
#if defined(LPUART4)
__HANDLERFUNC void LPUART4_Handler(void)
{ pCallbackLPUART[4](LPUART4, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART4)); 
}
#endif
#if defined(LPUART5)
__HANDLERFUNC void LPUART5_Handler(void)
{ 
  pCallbackLPUART[5](LPUART5, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART5)); 
}
#endif
#if defined(LPUART6)
__HANDLERFUNC void LPUART6_Handler(void)
{ 
  pCallbackLPUART[6](LPUART6, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART6)); 
}
#endif
#if defined(LPUART7)
__HANDLERFUNC void LPUART7_Handler(void)
{ 
  pCallbackLPUART[7](LPUART7, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART7)); 
}
#endif
#if defined(LPUART8)
__HANDLERFUNC void LPUART8_Handler(void)
{ 
  pCallbackLPUART[8](LPUART8, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART8)); 
}
#endif
#if defined(LPUART9)
__HANDLERFUNC void LPUART9_Handler(void)
{ 
  pCallbackLPUART[9](LPUART9, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART9)); 
}
#endif
#if defined(LPUART10)
__HANDLERFUNC void LPUART10_Handler(void)
{ 
  pCallbackLPUART[10](LPUART10, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART10)); 
}
#endif
#if defined(LPUART11)
__HANDLERFUNC void LPUART11_Handler(void)
{ 
  pCallbackLPUART[11](LPUART11, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART11)); 
}
#endif
#if defined(LPUART12)
__HANDLERFUNC void LPUART12_Handler(void)
{ 
  pCallbackLPUART[12](LPUART12, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART12)); 
}
#endif
#if defined(LPUART13)
__HANDLERFUNC void LPUART13_Handler(void)
{ 
  pCallbackLPUART[13](LPUART13, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART13)); }
#endif
#if defined(LPUART14)

__HANDLERFUNC void LPUART14_Handler(void)
{ 
  pCallbackLPUART[14](LPUART14, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART14)); 
}
#endif
#if defined(LPUART15)
__HANDLERFUNC void LPUART15_Handler(void)
{ 
  pCallbackLPUART[15](LPUART15, (tLPUART_CALLBACK_TYPE)LPUART_GetClrIrqFlags(LPUART15)); 
}
#endif
/******************************************************************************
 * End of module                                                              *
 ******************************************************************************/
