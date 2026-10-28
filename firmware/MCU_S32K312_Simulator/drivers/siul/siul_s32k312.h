/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      siul_s32k312.h
 * @brief     System Integration Unit Lite2 (SIUL) private init macro derived from
 *            S32K312_io_signal_table_flat_signal_table_scsource_Customer_Rev1.0.xlsx.
 */
#ifndef __SIUL_S32K312_H
#define __SIUL_S32K312_H

#define VSIUL_prvInit(slot,port,pins,fcns,cfg)\
do{\
  register uint32_t __t = fcns;\
  if((port) & PTA)\
  {\
    if((pins) & PIN0)\
    {\
      prvVSIUL[slot]->MSCR[0] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[0]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[17]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_OBE_MASK|0x3U; /*LCU0_OUT4*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D2*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_OBE_MASK|0x5U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_PCS7*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT3*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S8*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin CMP1_IN0*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[16] = 0x1U; /*EIRQ[0]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[65] = 0x2U; /*eMIOS_0_CH[17]_Y*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[80] = 0x3U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0x2U; /*FXIO_D2*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[228] = 0x1U; /*LPSPI0_PCS7*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[360] = 0x1U; /*LPUART0_CTS*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[0] = (prvVSIUL[slot]->MSCR[0])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN1)\
    {\
      prvVSIUL[slot]->MSCR[1] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[1]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[9]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPUART0_RTS*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D3*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT5*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_PCS6*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT0*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S9*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin CMP1_IN1*/\
      }\
      if(__t & INP_ALT2)\
      {\
      /*Direct pin WKPU[5]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[17] = 0x1U; /*EIRQ[1]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[57] = 0x1U; /*eMIOS_0_CH[9]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[155] = 0x1U; /*FXIO_D3*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[227] = 0x1U; /*LPSPI0_PCS6*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[1] = (prvVSIUL[slot]->MSCR[1])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN2)\
    {\
      prvVSIUL[slot]->MSCR[2] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[2]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_OBE_MASK|0x1U; /*FCCU_ERR0*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[19]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D4*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT3*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_X[0]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[0]*/\
      }\
      if(__t & INP_ALT2)\
      {\
      /*Direct pin CMP1_IN2*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[18] = 0x1U; /*EIRQ[2]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[99] = 0x4U; /*eMIOS_1_CH[19]_Y*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[148] = 0x1U; /*FCCU_ERR_IN0*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[156] = 0x3U; /*FXIO_D4*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[187] = 0x1U; /*LPUART0_RX*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[239] = 0x2U; /*LPSPI1_SIN*/\
      }\
      if(__t & (INP_ALT9 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[2] = (prvVSIUL[slot]->MSCR[2])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN3)\
    {\
      prvVSIUL[slot]->MSCR[3] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[3]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_OBE_MASK|0x1U; /*FCCU_ERR1*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[20]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_SCK*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_OBE_MASK|0x4U; /*LCU0_OUT2*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D5*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPUART0_TX*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S17*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[19] = 0x1U; /*EIRQ[3]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[100] = 0x4U; /*eMIOS_1_CH[20]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[149] = 0x1U; /*FCCU_ERR_IN1*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x3U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[238] = 0x1U; /*LPSPI1_SCK*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[363] = 0x1U; /*LPUART0_TX*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[3] = (prvVSIUL[slot]->MSCR[3])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN4)\
    {\
      prvVSIUL[slot]->MSCR[4] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[4]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D6*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_OBE_MASK|0x4U; /*CMP0_OUT*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_OBE_MASK|0x7U; /*JTAG_TMS/SWD_DIO*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S15*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[20] = 0x1U; /*EIRQ[4]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x8U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[186] = 0x0U; /*JTAG_TMS/SWD_DIO*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[4] = (prvVSIUL[slot]->MSCR[4])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN5)\
    {\
      prvVSIUL[slot]->MSCR[5] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[5] = (prvVSIUL[slot]->MSCR[5])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[5]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[5] = (prvVSIUL[slot]->MSCR[5])|SIUL2_MSCR_OBE_MASK|0x7U; /*RESET_b*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[5] = (prvVSIUL[slot]->MSCR[5])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[21] = 0x1U; /*EIRQ[5]*/\
      }\
      if(__t & (INP_ALT1 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[5] = (prvVSIUL[slot]->MSCR[5])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN6)\
    {\
      prvVSIUL[slot]->MSCR[6] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[6]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS1*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_1_CH[13]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D19*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI3_PCS1*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[15]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_S18*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[0] = 0x2U; /*CAN0_RX*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[22] = 0x1U; /*EIRQ[6]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[93] = 0x1U; /*eMIOS_1_CH[13]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[171] = 0x4U; /*FXIO_D19*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[190] = 0x2U; /*LPUART3_RX*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[233] = 0x1U; /*LPSPI1_PCS1*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[249] = 0x5U; /*LPSPI3_PCS1*/\
      }\
      if(__t & INP_ALT9)\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[361] = 0x2U; /*LPUART1_CTS*/\
      }\
      if(__t & (INP_ALT10 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[6] = (prvVSIUL[slot]->MSCR[6])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN7)\
    {\
      prvVSIUL[slot]->MSCR[7] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[7]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPUART3_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI0_PCS1*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[11]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_OBE_MASK|0x4U; /*CAN0_TX*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPUART1_RTS*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D9*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S11*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[23] = 0x1U; /*EIRQ[7]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[91] = 0x1U; /*eMIOS_1_CH[11]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[161] = 0x3U; /*FXIO_D9*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[222] = 0x3U; /*LPSPI0_PCS1*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[366] = 0x1U; /*LPUART3_TX*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[7] = (prvVSIUL[slot]->MSCR[7])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN8)\
    {\
      prvVSIUL[slot]->MSCR[8] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[8]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_SOUT*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[23]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_P2*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[32] = 0x1U; /*EIRQ[16]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[92] = 0x2U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x2U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[189] = 0x3U; /*LPUART2_RX*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[247] = 0x1U; /*LPSPI2_SOUT*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[8] = (prvVSIUL[slot]->MSCR[8])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN9)\
    {\
      prvVSIUL[slot]->MSCR[9] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[9]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPUART2_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_PCS0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D7*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI3_PCS0*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[21]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_P7*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[33] = 0x1U; /*EIRQ[17]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x2U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[241] = 0x1U; /*LPSPI2_PCS0*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[248] = 0x3U; /*LPSPI3_PCS0*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[365] = 0x1U; /*LPUART2_TX*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[9] = (prvVSIUL[slot]->MSCR[9])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN10)\
    {\
      prvVSIUL[slot]->MSCR[10] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[10]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[12]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_OBE_MASK|0x7U; /*JTAG_TDO/TRACEnoETM_SWO*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[34] = 0x1U; /*EIRQ[18]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[60] = 0x2U; /*eMIOS_0_CH[12]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[152] = 0x2U; /*FXIO_D0*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[10] = (prvVSIUL[slot]->MSCR[10])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN11)\
    {\
      prvVSIUL[slot]->MSCR[11] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[11]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN1_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[13]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D1*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_OBE_MASK|0x5U; /*CMP0_RRT*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI1_PCS0*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S10*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[35] = 0x1U; /*EIRQ[19]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[61] = 0x1U; /*eMIOS_0_CH[13]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[81] = 0x3U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[153] = 0x2U; /*FXIO_D1*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[232] = 0x2U; /*LPSPI1_PCS0*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[11] = (prvVSIUL[slot]->MSCR[11])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN12)\
    {\
      prvVSIUL[slot]->MSCR[12] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[12]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI1_PCS5*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[14]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_OBE_MASK|0x3U; /*CLKOUT_STANDBY*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D9*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_OBE_MASK|0x7U; /*CMP1_OUT*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_P0*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[1] = 0x2U; /*CAN1_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[36] = 0x1U; /*EIRQ[20]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[62] = 0x1U; /*eMIOS_0_CH[14]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[82] = 0x4U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[161] = 0x4U; /*FXIO_D9*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[237] = 0x1U; /*LPSPI1_PCS5*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[12] = (prvVSIUL[slot]->MSCR[12])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN13)\
    {\
      prvVSIUL[slot]->MSCR[13] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[13]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI1_PCS4*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[15]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D8*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[4]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_P1*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[37] = 0x1U; /*EIRQ[21]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[63] = 0x2U; /*eMIOS_0_CH[15]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[83] = 0x4U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[160] = 0x4U; /*FXIO_D8*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[236] = 0x1U; /*LPSPI1_PCS4*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[13] = (prvVSIUL[slot]->MSCR[13])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN14)\
    {\
      prvVSIUL[slot]->MSCR[14] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[14]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS3*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D14*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_P4*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[38] = 0x1U; /*EIRQ[22]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[84] = 0x7U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[166] = 0x4U; /*FXIO_D14*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[235] = 0x2U; /*LPSPI1_PCS3*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[14] = (prvVSIUL[slot]->MSCR[14])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN15)\
    {\
      prvVSIUL[slot]->MSCR[15] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[15]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[10]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI0_PCS3*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI2_PCS3*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D31*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_P7*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[20]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[39] = 0x1U; /*EIRQ[23]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[58] = 0x2U; /*eMIOS_0_CH[10]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[183] = 0x1U; /*FXIO_D31*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[193] = 0x2U; /*LPUART6_RX*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[224] = 0x1U; /*LPSPI0_PCS3*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[244] = 0x1U; /*LPSPI2_PCS3*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[15] = (prvVSIUL[slot]->MSCR[15])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN16)\
    {\
      prvVSIUL[slot]->MSCR[16] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[16]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[11]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS2*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_PCS4*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPUART6_TX*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D30*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S13*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[31]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[20] = 0x2U; /*EIRQ[4]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[59] = 0x2U; /*eMIOS_0_CH[11]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[182] = 0x1U; /*FXIO_D30*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[225] = 0x1U; /*LPSPI0_PCS4*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[234] = 0x2U; /*LPSPI1_PCS2*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[369] = 0x1U; /*LPUART6_TX*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[16] = (prvVSIUL[slot]->MSCR[16])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN17)\
    {\
      prvVSIUL[slot]->MSCR[17] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[17]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[6]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPUART4_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI3_SOUT*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D19*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[54] = 0x2U; /*eMIOS_0_CH[6]_G*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[171] = 0x1U; /*FXIO_D19*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[254] = 0x2U; /*LPSPI3_SOUT*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[367] = 0x1U; /*LPUART4_TX*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[17] = (prvVSIUL[slot]->MSCR[17])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN18)\
    {\
      prvVSIUL[slot]->MSCR[18] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[18]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPUART1_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI1_SOUT*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_OBE_MASK|0x5U; /*eMIOS_1_CH[16]_X*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[16] = 0x2U; /*EIRQ[0]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[80] = 0x1U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[96] = 0x1U; /*eMIOS_1_CH[16]_X*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[240] = 0x4U; /*LPSPI1_SOUT*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[356] = 0x1U; /*TRGMUX_IN12*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[364] = 0x4U; /*LPUART1_TX*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[18] = (prvVSIUL[slot]->MSCR[18])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN19)\
    {\
      prvVSIUL[slot]->MSCR[19] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[19]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI1_SCK*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[17] = 0x2U; /*EIRQ[1]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[81] = 0x1U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[188] = 0x5U; /*LPUART1_RX*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[238] = 0x3U; /*LPSPI1_SCK*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[357] = 0x1U; /*TRGMUX_IN13*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[19] = (prvVSIUL[slot]->MSCR[19])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN20)\
    {\
      prvVSIUL[slot]->MSCR[20] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[20]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI1_SIN*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[59]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[18] = 0x2U; /*EIRQ[2]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[82] = 0x2U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[239] = 0x3U; /*LPSPI1_SIN*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[358] = 0x1U; /*TRGMUX_IN14*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[20] = (prvVSIUL[slot]->MSCR[20])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN21)\
    {\
      prvVSIUL[slot]->MSCR[21] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[21]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI2_PCS2*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D0*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI1_PCS0*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[19] = 0x2U; /*EIRQ[3]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[83] = 0x1U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[152] = 0x3U; /*FXIO_D0*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[232] = 0x3U; /*LPSPI1_PCS0*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[243] = 0x1U; /*LPSPI2_PCS2*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[359] = 0x1U; /*TRGMUX_IN15*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[21] = (prvVSIUL[slot]->MSCR[21])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN22)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN23)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN24)\
    {\
      prvVSIUL[slot]->MSCR[24] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[24] = (prvVSIUL[slot]->MSCR[24])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPI[24]*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin OSC32K_XTAL*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[24] = (prvVSIUL[slot]->MSCR[24])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[87] = 0x2U; /*eMIOS_1_CH[7]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[24] = (prvVSIUL[slot]->MSCR[24])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[155] = 0x3U; /*FXIO_D3*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[24] = (prvVSIUL[slot]->MSCR[24])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN25)\
    {\
      prvVSIUL[slot]->MSCR[25] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[25] = (prvVSIUL[slot]->MSCR[25])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPI[25]*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin OSC32K_EXTAL*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[34]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[25] = (prvVSIUL[slot]->MSCR[25])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[21] = 0x2U; /*EIRQ[5]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[25] = (prvVSIUL[slot]->MSCR[25])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[88] = 0x2U; /*eMIOS_1_CH[8]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[25] = (prvVSIUL[slot]->MSCR[25])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0x6U; /*FXIO_D2*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[25] = (prvVSIUL[slot]->MSCR[25])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN26)\
    {\
      prvVSIUL[slot]->MSCR[26] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[26]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[9]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_PCS0*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D1*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[35]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[89] = 0x2U; /*eMIOS_1_CH[9]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[153] = 0x7U; /*FXIO_D1*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[221] = 0x3U; /*LPSPI0_PCS0*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[232] = 0x5U; /*LPSPI1_PCS0*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[26] = (prvVSIUL[slot]->MSCR[26])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN27)\
    {\
      prvVSIUL[slot]->MSCR[27] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[27]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_OBE_MASK|0x1U; /*FXIO_D5*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPUART0_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_OBE_MASK|0x5U; /*CAN0_TX*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[90] = 0x3U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x9U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[363] = 0x4U; /*LPUART0_TX*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[27] = (prvVSIUL[slot]->MSCR[27])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN28)\
    {\
      prvVSIUL[slot]->MSCR[28] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[28]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[11]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_SCK*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[0] = 0x4U; /*CAN0_RX*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[22] = 0x2U; /*EIRQ[6]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[91] = 0x2U; /*eMIOS_1_CH[11]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[187] = 0x4U; /*LPUART0_RX*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[238] = 0x4U; /*LPSPI1_SCK*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[28] = (prvVSIUL[slot]->MSCR[28])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN29)\
    {\
      prvVSIUL[slot]->MSCR[29] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[29]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPUART2_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI1_SIN*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[92] = 0x3U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[239] = 0x4U; /*LPSPI1_SIN*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[365] = 0x5U; /*LPUART2_TX*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[29] = (prvVSIUL[slot]->MSCR[29])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN30)\
    {\
      prvVSIUL[slot]->MSCR[30] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[30]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[13]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_SOUT*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_SOUT*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[37]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[23] = 0x2U; /*EIRQ[7]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[93] = 0x2U; /*eMIOS_1_CH[13]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[189] = 0x4U; /*LPUART2_RX*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[231] = 0x4U; /*LPSPI0_SOUT*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[240] = 0x5U; /*LPSPI1_SOUT*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[30] = (prvVSIUL[slot]->MSCR[30])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN31)\
    {\
      prvVSIUL[slot]->MSCR[31] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[31]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_PCS1*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT8*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[94] = 0x2U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[152] = 0x6U; /*FXIO_D0*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[222] = 0x2U; /*LPSPI0_PCS1*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[31] = (prvVSIUL[slot]->MSCR[31])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
  }\
  if((port) & PTB)\
  {\
    if((pins) & PIN0)\
    {\
      prvVSIUL[slot]->MSCR[32] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[32]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPI2C0_SDAS*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x2U; /*FXIO_D14*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI0_PCS0*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU1_OUT5*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_1_CH[6]_H*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_OBE_MASK|0x7U; /*HSE_TAMPER_LOOP_OUT0 */\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S14*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_S14*/\
      }\
      if(__t & INP_ALT2)\
      {\
      /*Direct pin WKPU[7]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[0] = 0x3U; /*CAN0_RX*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[24] = 0x1U; /*EIRQ[8]*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[51] = 0x4U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[86] = 0x1U; /*eMIOS_1_CH[6]_H*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[166] = 0x3U; /*FXIO_D14*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[187] = 0x2U; /*LPUART0_RX*/\
      }\
      if(__t & INP_ALT9)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[215] = 0x1U; /*LPI2C0_SDAS*/\
      }\
      if(__t & INP_ALT10)\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[221] = 0x1U; /*LPSPI0_PCS0*/\
      }\
      if(__t & (INP_ALT11 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[32] = (prvVSIUL[slot]->MSCR[32])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN1)\
    {\
      prvVSIUL[slot]->MSCR[33] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[33]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPI2C0_SCLS*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPUART0_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI0_SOUT*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[7]_G*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x5U; /*CAN0_TX*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_OBE_MASK|0x7U; /*LCU1_OUT4*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S15*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_S15*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[25] = 0x1U; /*EIRQ[9]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[55] = 0x3U; /*eMIOS_0_CH[7]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[85] = 0x1U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[213] = 0x1U; /*LPI2C0_SCLS*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[231] = 0x3U; /*LPSPI0_SOUT*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[343] = 0x1U; /*HSE_TAMPER_EXTIN0*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[363] = 0x2U; /*LPUART0_TX*/\
      }\
      if(__t & (INP_ALT9 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[33] = (prvVSIUL[slot]->MSCR[33])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN2)\
    {\
      prvVSIUL[slot]->MSCR[34] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[34]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_OBE_MASK|0x1U; /*ADC1_MA[0]*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[8]_X*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_SIN*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU1_OUT3*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D18*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[8]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[4] = 0x2U; /*CAN4_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[26] = 0x1U; /*EIRQ[10]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[56] = 0x1U; /*eMIOS_0_CH[8]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[170] = 0x1U; /*FXIO_D18*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[246] = 0x2U; /*LPSPI2_SIN*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[347] = 0x1U; /*TRGMUX_IN3*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[34] = (prvVSIUL[slot]->MSCR[34])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN3)\
    {\
      prvVSIUL[slot]->MSCR[35] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[35]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[9]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_SOUT*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_OBE_MASK|0x4U; /*ADC0_MA[0]*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_OBE_MASK|0x5U; /*CAN4_TX*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT2*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D17*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[27] = 0x1U; /*EIRQ[11]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[57] = 0x2U; /*eMIOS_0_CH[9]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[169] = 0x1U; /*FXIO_D17*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[247] = 0x2U; /*LPSPI2_SOUT*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[346] = 0x1U; /*TRGMUX_IN2*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[35] = (prvVSIUL[slot]->MSCR[35])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN4)\
    {\
      prvVSIUL[slot]->MSCR[36] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[36]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[4]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI0_SOUT*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[28] = 0x1U; /*EIRQ[12]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[52] = 0x1U; /*eMIOS_0_CH[4]_G*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[90] = 0x6U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[231] = 0x2U; /*LPSPI0_SOUT*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[345] = 0x1U; /*TRGMUX_IN1*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[36] = (prvVSIUL[slot]->MSCR[36])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN5)\
    {\
      prvVSIUL[slot]->MSCR[37] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[37]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[5]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI0_PCS1*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_PCS0*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_OBE_MASK|0x5U; /*CLKOUT_RUN*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_1_CH[11]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[29] = 0x1U; /*EIRQ[13]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[53] = 0x1U; /*eMIOS_0_CH[5]_G*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[91] = 0x5U; /*eMIOS_1_CH[11]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[221] = 0x2U; /*LPSPI0_PCS0*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[222] = 0x1U; /*LPSPI0_PCS1*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[344] = 0x1U; /*TRGMUX_IN0*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[37] = (prvVSIUL[slot]->MSCR[37])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN6)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN7)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN8)\
    {\
      prvVSIUL[slot]->MSCR[40] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[40]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT11*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_PCS5*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D29*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_X[0]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[25]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[30] = 0x1U; /*EIRQ[14]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[95] = 0x6U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[181] = 0x1U; /*FXIO_D29*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[226] = 0x1U; /*LPSPI0_PCS5*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[40] = (prvVSIUL[slot]->MSCR[40])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN9)\
    {\
      prvVSIUL[slot]->MSCR[41] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[41]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[16]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT10*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D28*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_X[1]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[17]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[31] = 0x1U; /*EIRQ[15]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[96] = 0x5U; /*eMIOS_1_CH[16]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[180] = 0x1U; /*FXIO_D28*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[41] = (prvVSIUL[slot]->MSCR[41])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN10)\
    {\
      prvVSIUL[slot]->MSCR[42] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[42]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[17]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT9*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D27*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_X[2]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[40] = 0x1U; /*EIRQ[24]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[97] = 0x4U; /*eMIOS_1_CH[17]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[179] = 0x1U; /*FXIO_D27*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[42] = (prvVSIUL[slot]->MSCR[42])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN11)\
    {\
      prvVSIUL[slot]->MSCR[43] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[43]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[18]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT8*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D26*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_X[3]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[16]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[41] = 0x1U; /*EIRQ[25]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[98] = 0x4U; /*eMIOS_1_CH[18]_Y*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[178] = 0x1U; /*FXIO_D26*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[211] = 0x1U; /*LPI2C0_HREQ*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[43] = (prvVSIUL[slot]->MSCR[43])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN12)\
    {\
      prvVSIUL[slot]->MSCR[44] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[44]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI3_PCS3*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[0]_X*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT2*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D25*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_X[1]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[12]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[42] = 0x1U; /*EIRQ[26]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[48] = 0x1U; /*eMIOS_0_CH[0]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[177] = 0x1U; /*FXIO_D25*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[251] = 0x1U; /*LPSPI3_PCS3*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[44] = (prvVSIUL[slot]->MSCR[44])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN13)\
    {\
      prvVSIUL[slot]->MSCR[45] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[45]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI3_PCS2*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D8*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT3*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D24*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S8*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_S8*/\
      }\
      if(__t & INP_ALT2)\
      {\
      /*Direct pin WKPU[11]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[43] = 0x1U; /*EIRQ[27]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[49] = 0x2U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[160] = 0x3U; /*FXIO_D8*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[176] = 0x1U; /*FXIO_D24*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[250] = 0x1U; /*LPSPI3_PCS2*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[45] = (prvVSIUL[slot]->MSCR[45])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN14)\
    {\
      prvVSIUL[slot]->MSCR[46] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[46]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_SCK*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_OBE_MASK|0x4U; /*LCU0_OUT7*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D23*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S9*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_S9*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[44] = 0x1U; /*EIRQ[28]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[50] = 0x3U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[175] = 0x1U; /*FXIO_D23*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[194] = 0x1U; /*LPUART7_RX*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[238] = 0x2U; /*LPSPI1_SCK*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[46] = (prvVSIUL[slot]->MSCR[46])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN15)\
    {\
      prvVSIUL[slot]->MSCR[47] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[47]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_SIN*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPUART7_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D22*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S11*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[33]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[45] = 0x1U; /*EIRQ[29]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[51] = 0x1U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[174] = 0x1U; /*FXIO_D22*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[239] = 0x1U; /*LPSPI1_SIN*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[370] = 0x1U; /*LPUART7_TX*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[47] = (prvVSIUL[slot]->MSCR[47])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN16)\
    {\
      prvVSIUL[slot]->MSCR[48] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[48]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[4]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_SOUT*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPUART4_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D21*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[13]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_S12*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[46] = 0x1U; /*EIRQ[30]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[52] = 0x2U; /*eMIOS_0_CH[4]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[173] = 0x1U; /*FXIO_D21*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[240] = 0x2U; /*LPSPI1_SOUT*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[367] = 0x2U; /*LPUART4_TX*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[48] = (prvVSIUL[slot]->MSCR[48])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN17)\
    {\
      prvVSIUL[slot]->MSCR[49] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[49]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[5]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS3*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_1_CH[7]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI3_PCS0*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D20*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_X[2]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[14]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[47] = 0x1U; /*EIRQ[31]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[53] = 0x2U; /*eMIOS_0_CH[5]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[87] = 0x7U; /*eMIOS_1_CH[7]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[172] = 0x1U; /*FXIO_D20*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[191] = 0x3U; /*LPUART4_RX*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[235] = 0x1U; /*LPSPI1_PCS3*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[248] = 0x2U; /*LPSPI3_PCS0*/\
      }\
      if(__t & (INP_ALT9 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[49] = (prvVSIUL[slot]->MSCR[49])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN18)\
    {\
      prvVSIUL[slot]->MSCR[50] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[50]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D1*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI1_PCS1*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT9*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[95] = 0x2U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[153] = 0x6U; /*FXIO_D1*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[233] = 0x2U; /*LPSPI1_PCS1*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[50] = (prvVSIUL[slot]->MSCR[50])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN19)\
    {\
      prvVSIUL[slot]->MSCR[51] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[51] = (prvVSIUL[slot]->MSCR[51])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[51]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[51] = (prvVSIUL[slot]->MSCR[51])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[51] = (prvVSIUL[slot]->MSCR[51])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D2*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[51] = (prvVSIUL[slot]->MSCR[51])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT10*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[38]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[51] = (prvVSIUL[slot]->MSCR[51])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[95] = 0x3U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[51] = (prvVSIUL[slot]->MSCR[51])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0x5U; /*FXIO_D2*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[51] = (prvVSIUL[slot]->MSCR[51])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN20)\
    {\
      prvVSIUL[slot]->MSCR[52] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[52] = (prvVSIUL[slot]->MSCR[52])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[52]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[52] = (prvVSIUL[slot]->MSCR[52])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[16]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[52] = (prvVSIUL[slot]->MSCR[52])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D3*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[52] = (prvVSIUL[slot]->MSCR[52])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT11*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[52] = (prvVSIUL[slot]->MSCR[52])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[96] = 0x3U; /*eMIOS_1_CH[16]_X*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[52] = (prvVSIUL[slot]->MSCR[52])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[155] = 0x5U; /*FXIO_D3*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[52] = (prvVSIUL[slot]->MSCR[52])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN21)\
    {\
      prvVSIUL[slot]->MSCR[53] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[53]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[17]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D4*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT12*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[39]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[24] = 0x2U; /*EIRQ[8]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[97] = 0x2U; /*eMIOS_1_CH[17]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[156] = 0x5U; /*FXIO_D4*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[53] = (prvVSIUL[slot]->MSCR[53])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN22)\
    {\
      prvVSIUL[slot]->MSCR[54] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[54]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN1_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[18]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI3_PCS1*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPUART1_TX*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D15*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT13*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[25] = 0x2U; /*EIRQ[9]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[98] = 0x2U; /*eMIOS_1_CH[18]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[167] = 0x5U; /*FXIO_D15*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[249] = 0x4U; /*LPSPI3_PCS1*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[364] = 0x5U; /*LPUART1_TX*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[54] = (prvVSIUL[slot]->MSCR[54])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN23)\
    {\
      prvVSIUL[slot]->MSCR[55] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[55]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_OBE_MASK|0x1U; /*ADC1_MA[0]*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[19]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D4*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT14*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[40]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[1] = 0x4U; /*CAN1_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[26] = 0x2U; /*EIRQ[10]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[99] = 0x2U; /*eMIOS_1_CH[19]_Y*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[156] = 0x6U; /*FXIO_D4*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[188] = 0x4U; /*LPUART1_RX*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[55] = (prvVSIUL[slot]->MSCR[55])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN24)\
    {\
      prvVSIUL[slot]->MSCR[56] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[56]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_OBE_MASK|0x1U; /*ADC1_MA[1]*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[20]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[27] = 0x2U; /*EIRQ[11]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[100] = 0x2U; /*eMIOS_1_CH[20]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x6U; /*FXIO_D5*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[56] = (prvVSIUL[slot]->MSCR[56])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN25)\
    {\
      prvVSIUL[slot]->MSCR[57] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[57]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[21]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D6*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI2_PCS0*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[28] = 0x2U; /*EIRQ[12]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[101] = 0x2U; /*eMIOS_1_CH[21]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x5U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[241] = 0x4U; /*LPSPI2_PCS0*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[57] = (prvVSIUL[slot]->MSCR[57])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN26)\
    {\
      prvVSIUL[slot]->MSCR[58] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[58] = (prvVSIUL[slot]->MSCR[58])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[58]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[58] = (prvVSIUL[slot]->MSCR[58])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[22]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[58] = (prvVSIUL[slot]->MSCR[58])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[41]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[58] = (prvVSIUL[slot]->MSCR[58])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[29] = 0x2U; /*EIRQ[13]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[58] = (prvVSIUL[slot]->MSCR[58])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[102] = 0x2U; /*eMIOS_1_CH[22]_X*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[58] = (prvVSIUL[slot]->MSCR[58])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x6U; /*FXIO_D7*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[58] = (prvVSIUL[slot]->MSCR[58])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN27)\
    {\
      prvVSIUL[slot]->MSCR[59] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[59]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPUART5_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[23]_X*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D8*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI2_SOUT*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[103] = 0x2U; /*eMIOS_1_CH[23]_X*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[160] = 0x2U; /*FXIO_D8*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[247] = 0x3U; /*LPSPI2_SOUT*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[368] = 0x3U; /*LPUART5_TX*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[59] = (prvVSIUL[slot]->MSCR[59])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN28)\
    {\
      prvVSIUL[slot]->MSCR[60] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[60]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_OBE_MASK|0x1U; /*ADC1_MA[2]*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D9*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI2_SIN*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT11*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[42]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[30] = 0x2U; /*EIRQ[14]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[161] = 0x2U; /*FXIO_D9*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[192] = 0x4U; /*LPUART5_RX*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[246] = 0x3U; /*LPSPI2_SIN*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[60] = (prvVSIUL[slot]->MSCR[60])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN29)\
    {\
      prvVSIUL[slot]->MSCR[61] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[61]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPUART6_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D10*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI2_SCK*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT10*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[162] = 0x2U; /*FXIO_D10*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[245] = 0x3U; /*LPSPI2_SCK*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[369] = 0x3U; /*LPUART6_TX*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[61] = (prvVSIUL[slot]->MSCR[61])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN30)\
    {\
      prvVSIUL[slot]->MSCR[62] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[62] = (prvVSIUL[slot]->MSCR[62])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[62]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[62] = (prvVSIUL[slot]->MSCR[62])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D11*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[62] = (prvVSIUL[slot]->MSCR[62])|SIUL2_MSCR_OBE_MASK|0x5U; /*HSE_TAMPER_LOOP_OUT0 */\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[62] = (prvVSIUL[slot]->MSCR[62])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[163] = 0x2U; /*FXIO_D11*/\
      }\
      if(__t & (INP_ALT1 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[62] = (prvVSIUL[slot]->MSCR[62])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN31)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
  }\
  if((port) & PTC)\
  {\
    if((pins) & PIN0)\
    {\
      prvVSIUL[slot]->MSCR[64] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[64]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN3_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[0]_X*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_0_CH[14]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[16] = 0x3U; /*EIRQ[0]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[48] = 0x3U; /*eMIOS_0_CH[0]_X*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[62] = 0x2U; /*eMIOS_0_CH[14]_H*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[64] = (prvVSIUL[slot]->MSCR[64])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN1)\
    {\
      prvVSIUL[slot]->MSCR[65] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[65]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D5*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_0_CH[15]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[3] = 0x2U; /*CAN3_RX*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[17] = 0x3U; /*EIRQ[1]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[49] = 0x1U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[63] = 0x1U; /*eMIOS_0_CH[15]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x7U; /*FXIO_D5*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[65] = (prvVSIUL[slot]->MSCR[65])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN2)\
    {\
      prvVSIUL[slot]->MSCR[66] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[66]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI3_PCS2*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_PCS2*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN2*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[0] = 0x1U; /*CAN0_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[18] = 0x3U; /*EIRQ[2]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[50] = 0x2U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[187] = 0x3U; /*LPUART0_RX*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[223] = 0x2U; /*LPSPI0_PCS2*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[250] = 0x4U; /*LPSPI3_PCS2*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[66] = (prvVSIUL[slot]->MSCR[66])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN3)\
    {\
      prvVSIUL[slot]->MSCR[67] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[67]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_OBE_MASK|0x3U; /*CAN0_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPUART0_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_OBE_MASK|0x5U; /*I3C0_PUR*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN4*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[19] = 0x3U; /*EIRQ[3]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[51] = 0x3U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[363] = 0x3U; /*LPUART0_TX*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[67] = (prvVSIUL[slot]->MSCR[67])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN4)\
    {\
      prvVSIUL[slot]->MSCR[68] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[68]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[8]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP1_IN3*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[20] = 0x3U; /*EIRQ[4]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[56] = 0x2U; /*eMIOS_0_CH[8]_X*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x8U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[184] = 0x0U; /*JTAG_TCK/SWD_CLK*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[68] = (prvVSIUL[slot]->MSCR[68])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN5)\
    {\
      prvVSIUL[slot]->MSCR[69] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[69]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[16]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D4*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S14*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[21] = 0x3U; /*EIRQ[5]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[64] = 0x2U; /*eMIOS_0_CH[16]_X*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[156] = 0x7U; /*FXIO_D4*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[185] = 0x0U; /*JTAG_TDI*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[216] = 0x2U; /*LPI2C1_HREQ*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[69] = (prvVSIUL[slot]->MSCR[69])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN6)\
    {\
      prvVSIUL[slot]->MSCR[70] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[70]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPI2C1_SDA*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x2U; /*FXIO_D11*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS1*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x4U; /*LCU0_OUT7*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x5U; /*eMIOS_1_CH[6]_H*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_PCS1*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_OBE_MASK|0x7U; /*ADC0_MA[2]*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[3]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_S18*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[2] = 0x6U; /*CAN2_RX*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[22] = 0x3U; /*EIRQ[6]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[86] = 0x4U; /*eMIOS_1_CH[6]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[163] = 0x3U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[188] = 0x1U; /*LPUART1_RX*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[219] = 0x2U; /*LPI2C1_SDA*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[222] = 0x4U; /*LPSPI0_PCS1*/\
      }\
      if(__t & INP_ALT9)\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[233] = 0x4U; /*LPSPI1_PCS1*/\
      }\
      if(__t & (INP_ALT10 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[70] = (prvVSIUL[slot]->MSCR[70])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN7)\
    {\
      prvVSIUL[slot]->MSCR[71] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[71]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x1U; /*FXIO_D10*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPUART1_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPI2C1_SCL*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x4U; /*LCU0_OUT6*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x5U; /*eMIOS_1_CH[7]_H*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_PCS0*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_OBE_MASK|0x7U; /*CAN2_TX*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[2]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_S16*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[23] = 0x3U; /*EIRQ[7]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[87] = 0x4U; /*eMIOS_1_CH[7]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[162] = 0x3U; /*FXIO_D10*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[211] = 0x2U; /*LPI2C0_HREQ*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[217] = 0x1U; /*LPI2C1_SCL*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[221] = 0x6U; /*LPSPI0_PCS0*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[364] = 0x1U; /*LPUART1_TX*/\
      }\
      if(__t & (INP_ALT9 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[71] = (prvVSIUL[slot]->MSCR[71])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN8)\
    {\
      prvVSIUL[slot]->MSCR[72] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[72]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPI2C0_SCL*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_OBE_MASK|0x3U; /*CAN1_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_1_CH[9]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU1_OUT7*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_SCK*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D12*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S12*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[32] = 0x2U; /*EIRQ[16]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[89] = 0x1U; /*eMIOS_1_CH[9]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[164] = 0x3U; /*FXIO_D12*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[188] = 0x2U; /*LPUART1_RX*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[212] = 0x1U; /*LPI2C0_SCL*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[229] = 0x1U; /*LPSPI0_SCK*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[360] = 0x2U; /*LPUART0_CTS*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[72] = (prvVSIUL[slot]->MSCR[72])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN9)\
    {\
      prvVSIUL[slot]->MSCR[73] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[73]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPI2C0_SDA*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPUART1_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPUART0_RTS*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_1_CH[8]_X*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU1_OUT6*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_SIN*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D13*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S13*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[10]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[1] = 0x1U; /*CAN1_RX*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[33] = 0x2U; /*EIRQ[17]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[88] = 0x1U; /*eMIOS_1_CH[8]_X*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[165] = 0x3U; /*FXIO_D13*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[214] = 0x1U; /*LPI2C0_SDA*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[230] = 0x2U; /*LPSPI0_SIN*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[364] = 0x2U; /*LPUART1_TX*/\
      }\
      if(__t & (INP_ALT9 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[73] = (prvVSIUL[slot]->MSCR[73])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN10)\
    {\
      prvVSIUL[slot]->MSCR[74] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[74]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_OBE_MASK|0x1U; /*eMIOS_0_CH[6]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_OBE_MASK|0x3U; /*CAN5_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI2_PCS1*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT11*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_OBE_MASK|0x7U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_X[3]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[34] = 0x2U; /*EIRQ[18]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[54] = 0x4U; /*eMIOS_0_CH[6]_G*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[80] = 0x6U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[242] = 0x3U; /*LPSPI2_PCS1*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[355] = 0x1U; /*TRGMUX_IN11*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[74] = (prvVSIUL[slot]->MSCR[74])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN11)\
    {\
      prvVSIUL[slot]->MSCR[75] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[75]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D15*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D19*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_OBE_MASK|0x7U; /*LCU1_OUT10*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[18]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_S17*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[5] = 0x2U; /*CAN5_RX*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[35] = 0x2U; /*EIRQ[19]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[81] = 0x7U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[167] = 0x3U; /*FXIO_D15*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[171] = 0x3U; /*FXIO_D19*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[354] = 0x1U; /*TRGMUX_IN10*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[75] = (prvVSIUL[slot]->MSCR[75])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN12)\
    {\
      prvVSIUL[slot]->MSCR[76] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[76]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_OBE_MASK|0x1U; /*ADC1_MA[2]*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_0_CH[22]_X*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI2_PCS1*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D19*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT9*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[36] = 0x2U; /*EIRQ[20]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[70] = 0x2U; /*eMIOS_0_CH[22]_X*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[82] = 0x1U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[171] = 0x5U; /*FXIO_D19*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[242] = 0x4U; /*LPSPI2_PCS1*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[76] = (prvVSIUL[slot]->MSCR[76])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN13)\
    {\
      prvVSIUL[slot]->MSCR[77] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[77]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_0_CH[23]_X*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_OBE_MASK|0x4U; /*ADC1_MA[1]*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D16*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT8*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[37] = 0x2U; /*EIRQ[21]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[71] = 0x1U; /*eMIOS_0_CH[23]_X*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[83] = 0x7U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[168] = 0x3U; /*FXIO_D16*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[77] = (prvVSIUL[slot]->MSCR[77])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN14)\
    {\
      prvVSIUL[slot]->MSCR[78] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[78]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[10]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_PCS0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_OBE_MASK|0x4U; /*ADC0_MA[1]*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_OBE_MASK|0x5U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT1*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D16*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[2] = 0x2U; /*CAN2_RX*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[38] = 0x2U; /*EIRQ[22]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[58] = 0x1U; /*eMIOS_0_CH[10]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[84] = 0x8U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[168] = 0x1U; /*FXIO_D16*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[241] = 0x2U; /*LPSPI2_PCS0*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[353] = 0x1U; /*TRGMUX_IN9*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[78] = (prvVSIUL[slot]->MSCR[78])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN15)\
    {\
      prvVSIUL[slot]->MSCR[79] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[79]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN2_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[11]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_SCK*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x4U; /*ADC0_MA[2]*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPUART2_TX*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT0*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_OBE_MASK|0x7U; /*LPI2C1_SCL*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[39] = 0x2U; /*EIRQ[23]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[59] = 0x1U; /*eMIOS_0_CH[11]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[217] = 0x6U; /*LPI2C1_SCL*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[245] = 0x2U; /*LPSPI2_SCK*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[352] = 0x1U; /*TRGMUX_IN8*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[365] = 0x2U; /*LPUART2_TX*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[79] = (prvVSIUL[slot]->MSCR[79])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN16)\
    {\
      prvVSIUL[slot]->MSCR[80] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[80]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI3_SIN*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[9]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPI2C1_SDAS*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_OBE_MASK|0x5U; /*I3C0_SCL*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D15*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_OBE_MASK|0x7U; /*LPI2C1_SDA*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[2] = 0x1U; /*CAN2_RX*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[89] = 0x5U; /*eMIOS_1_CH[9]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[167] = 0x1U; /*FXIO_D15*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[189] = 0x5U; /*LPUART2_RX*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[219] = 0x5U; /*LPI2C1_SDA*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[220] = 0x1U; /*LPI2C1_SDAS*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[253] = 0x3U; /*LPSPI3_SIN*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[371] = 0x2U; /*I3C0_SCL*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[80] = (prvVSIUL[slot]->MSCR[80])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN17)\
    {\
      prvVSIUL[slot]->MSCR[81] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[81]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI3_SCK*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_OBE_MASK|0x2U; /*I3C0_PUR*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_OBE_MASK|0x3U; /*CAN2_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPI2C1_SCLS*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D14*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D2*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0xaU; /*FXIO_D2*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[166] = 0x1U; /*FXIO_D14*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[218] = 0x2U; /*LPI2C1_SCLS*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[252] = 0x3U; /*LPSPI3_SCK*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[81] = (prvVSIUL[slot]->MSCR[81])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN18)\
    {\
      prvVSIUL[slot]->MSCR[82] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[82]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_OBE_MASK|0x2U; /*FXIO_D6*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D12*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT7*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[36]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x9U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[164] = 0x2U; /*FXIO_D12*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[193] = 0x4U; /*LPUART6_RX*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[82] = (prvVSIUL[slot]->MSCR[82])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN19)\
    {\
      prvVSIUL[slot]->MSCR[83] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[83]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPUART7_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D13*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI2_PCS1*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT6*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[165] = 0x2U; /*FXIO_D13*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[242] = 0x2U; /*LPSPI2_PCS1*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[370] = 0x2U; /*LPUART7_TX*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[83] = (prvVSIUL[slot]->MSCR[83])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN20)\
    {\
      prvVSIUL[slot]->MSCR[84] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[84]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D14*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_OBE_MASK|0x5U; /*ADC1_MA[2]*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT5*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[43]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[32] = 0x3U; /*EIRQ[16]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[166] = 0x2U; /*FXIO_D14*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[194] = 0x4U; /*LPUART7_RX*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[84] = (prvVSIUL[slot]->MSCR[84])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN21)\
    {\
      prvVSIUL[slot]->MSCR[85] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[85] = (prvVSIUL[slot]->MSCR[85])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[85]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[85] = (prvVSIUL[slot]->MSCR[85])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D15*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[85] = (prvVSIUL[slot]->MSCR[85])|SIUL2_MSCR_OBE_MASK|0x5U; /*ADC1_MA[1]*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[85] = (prvVSIUL[slot]->MSCR[85])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT4*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[85] = (prvVSIUL[slot]->MSCR[85])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[33] = 0x3U; /*EIRQ[17]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[85] = (prvVSIUL[slot]->MSCR[85])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[167] = 0x2U; /*FXIO_D15*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[85] = (prvVSIUL[slot]->MSCR[85])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN22)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN23)\
    {\
      prvVSIUL[slot]->MSCR[87] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[87] = (prvVSIUL[slot]->MSCR[87])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[87]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[87] = (prvVSIUL[slot]->MSCR[87])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D16*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[87] = (prvVSIUL[slot]->MSCR[87])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT0*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[44]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[87] = (prvVSIUL[slot]->MSCR[87])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[34] = 0x3U; /*EIRQ[18]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[87] = (prvVSIUL[slot]->MSCR[87])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[168] = 0x2U; /*FXIO_D16*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[87] = (prvVSIUL[slot]->MSCR[87])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN24)\
    {\
      prvVSIUL[slot]->MSCR[88] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[88]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D17*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT1*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT15*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[46]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[35] = 0x3U; /*EIRQ[19]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[80] = 0x4U; /*eMIOS_1_CH[0]_X*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[169] = 0x2U; /*FXIO_D17*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[88] = (prvVSIUL[slot]->MSCR[88])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN25)\
    {\
      prvVSIUL[slot]->MSCR[89] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[89]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D18*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT2*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S20*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[45]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[36] = 0x3U; /*EIRQ[20]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[81] = 0x4U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[170] = 0x2U; /*FXIO_D18*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[89] = (prvVSIUL[slot]->MSCR[89])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN26)\
    {\
      prvVSIUL[slot]->MSCR[90] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[90]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D19*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT9*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S21*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[48]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[5] = 0x5U; /*CAN5_RX*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[37] = 0x3U; /*EIRQ[21]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[83] = 0x3U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[171] = 0x2U; /*FXIO_D19*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[90] = (prvVSIUL[slot]->MSCR[90])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN27)\
    {\
      prvVSIUL[slot]->MSCR[91] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[91]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN5_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D20*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_OBE_MASK|0x5U; /*ADC1_MA[0]*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT3*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[38] = 0x3U; /*EIRQ[22]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[84] = 0x2U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[172] = 0x2U; /*FXIO_D20*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[91] = (prvVSIUL[slot]->MSCR[91])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN28)\
    {\
      prvVSIUL[slot]->MSCR[92] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[92]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN3_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[7]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D21*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D2*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPI2C1_SCL*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU1_OUT8*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_OBE_MASK|0x7U; /*I3C0_SCL*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[87] = 0x3U; /*eMIOS_1_CH[7]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0x7U; /*FXIO_D2*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[173] = 0x2U; /*FXIO_D21*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[217] = 0x4U; /*LPI2C1_SCL*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[371] = 0x3U; /*I3C0_SCL*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[92] = (prvVSIUL[slot]->MSCR[92])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN29)\
    {\
      prvVSIUL[slot]->MSCR[93] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[93]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D22*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPI2C1_SDA*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_OBE_MASK|0x6U; /*I3C0_SDA*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D3*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[47]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[3] = 0x3U; /*CAN3_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[39] = 0x3U; /*EIRQ[23]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[90] = 0x1U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[155] = 0x6U; /*FXIO_D3*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[174] = 0x2U; /*FXIO_D22*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[219] = 0x3U; /*LPI2C1_SDA*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[372] = 0x3U; /*I3C0_SDA*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[93] = (prvVSIUL[slot]->MSCR[93])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN30)\
    {\
      prvVSIUL[slot]->MSCR[94] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[94]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN4_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D0*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_OBE_MASK|0x5U; /*I3C0_PUR*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D23*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[92] = 0x1U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[152] = 0x4U; /*FXIO_D0*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[175] = 0x2U; /*FXIO_D23*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[94] = (prvVSIUL[slot]->MSCR[94])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN31)\
    {\
      prvVSIUL[slot]->MSCR[95] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[95]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D1*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D24*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[49]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[4] = 0x3U; /*CAN4_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[94] = 0x1U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[153] = 0x4U; /*FXIO_D1*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[176] = 0x2U; /*FXIO_D24*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[95] = (prvVSIUL[slot]->MSCR[95])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
  }\
  if((port) & PTD)\
  {\
    if((pins) & PIN0)\
    {\
      prvVSIUL[slot]->MSCR[96] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[96]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI3_SOUT*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[16]_X*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D0*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT1*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[6]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_P1*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[24] = 0x3U; /*EIRQ[8]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[50] = 0x1U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[64] = 0x1U; /*eMIOS_0_CH[16]_X*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[152] = 0x1U; /*FXIO_D0*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[192] = 0x2U; /*LPUART5_RX*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[254] = 0x1U; /*LPSPI3_SOUT*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[96] = (prvVSIUL[slot]->MSCR[96])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN1)\
    {\
      prvVSIUL[slot]->MSCR[97] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[97]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPUART5_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI3_SCK*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[17]_Y*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D1*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT2*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_P0*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[25] = 0x3U; /*EIRQ[9]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[51] = 0x2U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[65] = 0x1U; /*eMIOS_0_CH[17]_Y*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[153] = 0x1U; /*FXIO_D1*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[252] = 0x1U; /*LPSPI3_SCK*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[368] = 0x1U; /*LPUART5_TX*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[97] = (prvVSIUL[slot]->MSCR[97])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN2)\
    {\
      prvVSIUL[slot]->MSCR[98] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[98]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_OBE_MASK|0x1U; /*LCU0_OUT1*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[21]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_SOUT*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D4*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D6*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPUART3_TX*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[9]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_S16*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[26] = 0x3U; /*EIRQ[10]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[101] = 0x4U; /*eMIOS_1_CH[21]_Y*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[156] = 0x1U; /*FXIO_D4*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x3U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[240] = 0x1U; /*LPSPI1_SOUT*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[349] = 0x1U; /*TRGMUX_IN5*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[366] = 0x2U; /*LPUART3_TX*/\
      }\
      if(__t & (INP_ALT9 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[98] = (prvVSIUL[slot]->MSCR[98])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN3)\
    {\
      prvVSIUL[slot]->MSCR[99] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[99]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[22]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D5*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D7*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT0*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin NMI_b*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[1]*/\
      }\
      if(__t & INP_ALT2)\
      {\
      /*Direct pin ADC0_S10*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[27] = 0x3U; /*EIRQ[11]*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[102] = 0x4U; /*eMIOS_1_CH[22]_X*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x2U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x3U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[190] = 0x3U; /*LPUART3_RX*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[232] = 0x1U; /*LPSPI1_PCS0*/\
      }\
      if(__t & INP_ALT9)\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[348] = 0x1U; /*TRGMUX_IN4*/\
      }\
      if(__t & (INP_ALT10 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[99] = (prvVSIUL[slot]->MSCR[99])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN4)\
    {\
      prvVSIUL[slot]->MSCR[100] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[100]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[23]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI1_PCS1*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT6*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S19*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[22]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[28] = 0x3U; /*EIRQ[12]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[103] = 0x4U; /*eMIOS_1_CH[23]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[233] = 0x6U; /*LPSPI1_PCS1*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[100] = (prvVSIUL[slot]->MSCR[100])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN5)\
    {\
      prvVSIUL[slot]->MSCR[101] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[101]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_OBE_MASK|0x4U; /*I3C0_SDA*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D15*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_OBE_MASK|0x7U; /*LPSPI0_PCS1*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[29] = 0x3U; /*EIRQ[13]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[50] = 0x4U; /*eMIOS_0_CH[2]_G*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[67] = 0x2U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[167] = 0x4U; /*FXIO_D15*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[222] = 0x5U; /*LPSPI0_PCS1*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[351] = 0x1U; /*TRGMUX_IN7*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[372] = 0x2U; /*I3C0_SDA*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[101] = (prvVSIUL[slot]->MSCR[101])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN6)\
    {\
      prvVSIUL[slot]->MSCR[102] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[102]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_OBE_MASK|0x2U; /*FXIO_D3*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D13*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_OBE_MASK|0x7U; /*LPSPI0_PCS0*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN7*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[30] = 0x3U; /*EIRQ[14]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[92] = 0x5U; /*eMIOS_1_CH[12]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[155] = 0x9U; /*FXIO_D3*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[165] = 0x1U; /*FXIO_D13*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[189] = 0x1U; /*LPUART2_RX*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[221] = 0x7U; /*LPSPI0_PCS0*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[102] = (prvVSIUL[slot]->MSCR[102])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN7)\
    {\
      prvVSIUL[slot]->MSCR[103] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[103]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPUART2_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI3_PCS3*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_PCS3*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN6*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[31] = 0x3U; /*EIRQ[15]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[224] = 0x2U; /*LPSPI0_PCS3*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[251] = 0x5U; /*LPSPI3_PCS3*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[365] = 0x3U; /*LPUART2_TX*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[103] = (prvVSIUL[slot]->MSCR[103])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN8)\
    {\
      prvVSIUL[slot]->MSCR[104] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[104]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI3_SOUT*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPI2C1_SDA*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_OBE_MASK|0x4U; /*I3C0_SDA*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D1*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_0_CH[12]_H*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[40] = 0x2U; /*EIRQ[24]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[60] = 0x1U; /*eMIOS_0_CH[12]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[153] = 0x5U; /*FXIO_D1*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[163] = 0x5U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[193] = 0x1U; /*LPUART6_RX*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[219] = 0x1U; /*LPI2C1_SDA*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[254] = 0x3U; /*LPSPI3_SOUT*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[372] = 0x1U; /*I3C0_SDA*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[104] = (prvVSIUL[slot]->MSCR[104])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN9)\
    {\
      prvVSIUL[slot]->MSCR[105] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[105]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPI2C1_SCL*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPUART6_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_OBE_MASK|0x5U; /*I3C0_SCL*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_OBE_MASK|0x6U; /*eMIOS_0_CH[13]_H*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D10*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[41] = 0x2U; /*EIRQ[25]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[61] = 0x2U; /*eMIOS_0_CH[13]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[152] = 0x5U; /*FXIO_D0*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[162] = 0x4U; /*FXIO_D10*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[217] = 0x2U; /*LPI2C1_SCL*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[369] = 0x2U; /*LPUART6_TX*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[371] = 0x1U; /*I3C0_SCL*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[105] = (prvVSIUL[slot]->MSCR[105])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN10)\
    {\
      prvVSIUL[slot]->MSCR[106] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[106]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[16]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI0_SIN*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_OBE_MASK|0x6U; /*CLKOUT_RUN*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[42] = 0x2U; /*EIRQ[26]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[64] = 0x3U; /*eMIOS_0_CH[16]_X*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[90] = 0x2U; /*eMIOS_1_CH[10]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[230] = 0x4U; /*LPSPI0_SIN*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[106] = (prvVSIUL[slot]->MSCR[106])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN11)\
    {\
      prvVSIUL[slot]->MSCR[107] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[107]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[17]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_SCK*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[43] = 0x2U; /*EIRQ[27]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[65] = 0x3U; /*eMIOS_0_CH[17]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[229] = 0x5U; /*LPSPI0_SCK*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[362] = 0x1U; /*LPUART2_CTS*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[107] = (prvVSIUL[slot]->MSCR[107])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN12)\
    {\
      prvVSIUL[slot]->MSCR[108] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[108]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[18]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPUART2_RTS*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI0_SOUT*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[44] = 0x2U; /*EIRQ[28]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[66] = 0x1U; /*eMIOS_0_CH[18]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[216] = 0x1U; /*LPI2C1_HREQ*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[231] = 0x5U; /*LPSPI0_SOUT*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[108] = (prvVSIUL[slot]->MSCR[108])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN13)\
    {\
      prvVSIUL[slot]->MSCR[109] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[109]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[20]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D7*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPI2C0_SDA*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[24]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[45] = 0x2U; /*EIRQ[29]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[68] = 0x1U; /*eMIOS_0_CH[20]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x7U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[188] = 0x3U; /*LPUART1_RX*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[214] = 0x2U; /*LPI2C0_SDA*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[109] = (prvVSIUL[slot]->MSCR[109])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN14)\
    {\
      prvVSIUL[slot]->MSCR[110] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[110]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[21]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPUART1_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPI2C0_SCL*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_OBE_MASK|0x6U; /*CMP0_RRT*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_OBE_MASK|0x7U; /*CLKOUT_RUN*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[46] = 0x3U; /*EIRQ[30]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[69] = 0x1U; /*eMIOS_0_CH[21]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[212] = 0x2U; /*LPI2C0_SCL*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[364] = 0x3U; /*LPUART1_TX*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[110] = (prvVSIUL[slot]->MSCR[110])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN15)\
    {\
      prvVSIUL[slot]->MSCR[111] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[111]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_OBE_MASK|0x1U; /*FXIO_D6*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[0]_X*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_SCK*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D10*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN1*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[3] = 0x1U; /*CAN3_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[47] = 0x2U; /*EIRQ[31]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[48] = 0x2U; /*eMIOS_0_CH[0]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[94] = 0x6U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x7U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[162] = 0x1U; /*FXIO_D10*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[229] = 0x3U; /*LPSPI0_SCK*/\
      }\
      if(__t & INP_ALT8)\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[362] = 0x2U; /*LPUART2_CTS*/\
      }\
      if(__t & (INP_ALT9 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[111] = (prvVSIUL[slot]->MSCR[111])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN16)\
    {\
      prvVSIUL[slot]->MSCR[112] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[112]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPSPI0_SIN*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_OBE_MASK|0x5U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPUART2_RTS*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN5*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[49] = 0x3U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[95] = 0x7U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[230] = 0x3U; /*LPSPI0_SIN*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[112] = (prvVSIUL[slot]->MSCR[112])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN17)\
    {\
      prvVSIUL[slot]->MSCR[113] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[113]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[18]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI3_PCS0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D9*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[5] = 0x1U; /*CAN5_RX*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[40] = 0x3U; /*EIRQ[24]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[66] = 0x3U; /*eMIOS_0_CH[18]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[161] = 0x1U; /*FXIO_D9*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[189] = 0x2U; /*LPUART2_RX*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[248] = 0x1U; /*LPSPI3_PCS0*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[113] = (prvVSIUL[slot]->MSCR[113])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN18)\
    {\
      prvVSIUL[slot]->MSCR[114] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[114] = (prvVSIUL[slot]->MSCR[114])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[114]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[114] = (prvVSIUL[slot]->MSCR[114])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN2_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[114] = (prvVSIUL[slot]->MSCR[114])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[114] = (prvVSIUL[slot]->MSCR[114])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D2*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[114] = (prvVSIUL[slot]->MSCR[114])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[95] = 0x1U; /*eMIOS_1_CH[15]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[114] = (prvVSIUL[slot]->MSCR[114])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0x4U; /*FXIO_D2*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[114] = (prvVSIUL[slot]->MSCR[114])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN19)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN20)\
    {\
      prvVSIUL[slot]->MSCR[116] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[116]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[17]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D25*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI1_PCS2*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI3_SIN*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S22*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[54]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[41] = 0x3U; /*EIRQ[25]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[97] = 0x1U; /*eMIOS_1_CH[17]_Y*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[177] = 0x2U; /*FXIO_D25*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[234] = 0x1U; /*LPSPI1_PCS2*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[253] = 0x2U; /*LPSPI3_SIN*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[116] = (prvVSIUL[slot]->MSCR[116])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN21)\
    {\
      prvVSIUL[slot]->MSCR[117] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[117]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[18]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D26*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT4*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_S23*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[42] = 0x3U; /*EIRQ[26]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[98] = 0x1U; /*eMIOS_1_CH[18]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[178] = 0x2U; /*FXIO_D26*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[117] = (prvVSIUL[slot]->MSCR[117])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN22)\
    {\
      prvVSIUL[slot]->MSCR[118] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[118]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[19]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D27*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT5*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[43] = 0x3U; /*EIRQ[27]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[99] = 0x1U; /*eMIOS_1_CH[19]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[179] = 0x2U; /*FXIO_D27*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[118] = (prvVSIUL[slot]->MSCR[118])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN23)\
    {\
      prvVSIUL[slot]->MSCR[119] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[119]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[20]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D28*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_OBE_MASK|0x5U; /*HSE_TAMPER_LOOP_OUT0 */\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT10*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[50]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[44] = 0x3U; /*EIRQ[28]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[100] = 0x1U; /*eMIOS_1_CH[20]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[180] = 0x2U; /*FXIO_D28*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[119] = (prvVSIUL[slot]->MSCR[119])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN24)\
    {\
      prvVSIUL[slot]->MSCR[120] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[120]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[21]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D29*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_OBE_MASK|0x6U; /*LCU0_OUT11*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S20*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[45] = 0x3U; /*EIRQ[29]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[101] = 0x1U; /*eMIOS_1_CH[21]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[181] = 0x2U; /*FXIO_D29*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[343] = 0x2U; /*HSE_TAMPER_EXTIN0*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[120] = (prvVSIUL[slot]->MSCR[120])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN25)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN26)\
    {\
      prvVSIUL[slot]->MSCR[122] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[122]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[23]_X*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D7*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D30*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_OBE_MASK|0x7U; /*LCU0_OUT0*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[103] = 0x1U; /*eMIOS_1_CH[23]_X*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x4U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[182] = 0x2U; /*FXIO_D30*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[122] = (prvVSIUL[slot]->MSCR[122])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN27)\
    {\
      prvVSIUL[slot]->MSCR[123] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[123] = (prvVSIUL[slot]->MSCR[123])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[123]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[123] = (prvVSIUL[slot]->MSCR[123])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D31*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[123] = (prvVSIUL[slot]->MSCR[123])|SIUL2_MSCR_OBE_MASK|0x7U; /*LCU0_OUT1*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S21*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[51]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[123] = (prvVSIUL[slot]->MSCR[123])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[46] = 0x2U; /*EIRQ[30]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[123] = (prvVSIUL[slot]->MSCR[123])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[183] = 0x2U; /*FXIO_D31*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[123] = (prvVSIUL[slot]->MSCR[123])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN28)\
    {\
      prvVSIUL[slot]->MSCR[124] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[124] = (prvVSIUL[slot]->MSCR[124])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[124]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[124] = (prvVSIUL[slot]->MSCR[124])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT2*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S22*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[124] = (prvVSIUL[slot]->MSCR[124])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[47] = 0x3U; /*EIRQ[31]*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[124] = (prvVSIUL[slot]->MSCR[124])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN29)\
    {\
      prvVSIUL[slot]->MSCR[125] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[125] = (prvVSIUL[slot]->MSCR[125])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[125]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[125] = (prvVSIUL[slot]->MSCR[125])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT3*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S23*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[52]*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[125] = (prvVSIUL[slot]->MSCR[125])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN30)\
    {\
      prvVSIUL[slot]->MSCR[126] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[126] = (prvVSIUL[slot]->MSCR[126])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[126]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[126] = (prvVSIUL[slot]->MSCR[126])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT8*/\
      }\
      if(__t & (INP_ALT0 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[126] = prvVSIUL[slot]->MSCR[126]|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN31)\
    {\
      prvVSIUL[slot]->MSCR[127] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[127] = (prvVSIUL[slot]->MSCR[127])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[127]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[127] = (prvVSIUL[slot]->MSCR[127])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D6*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[127] = (prvVSIUL[slot]->MSCR[127])|SIUL2_MSCR_OBE_MASK|0x5U; /*LCU0_OUT9*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[53]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[127] = (prvVSIUL[slot]->MSCR[127])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x4U; /*FXIO_D6*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[127] = (prvVSIUL[slot]->MSCR[127])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
  }\
  if((port) & PTE)\
  {\
    if((pins) & PIN0)\
    {\
      prvVSIUL[slot]->MSCR[128] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[128]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI0_SIN*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D3*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[26]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_P2*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[16] = 0x4U; /*EIRQ[0]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[155] = 0x7U; /*FXIO_D3*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[194] = 0x2U; /*LPUART7_RX*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[230] = 0x1U; /*LPSPI0_SIN*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[128] = (prvVSIUL[slot]->MSCR[128])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN1)\
    {\
      prvVSIUL[slot]->MSCR[129] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[129]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI0_SCK*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D2*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPUART7_TX*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_P3*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[17] = 0x4U; /*EIRQ[1]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0x8U; /*FXIO_D2*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[229] = 0x2U; /*LPSPI0_SCK*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[370] = 0x3U; /*LPUART7_TX*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[129] = (prvVSIUL[slot]->MSCR[129])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN2)\
    {\
      prvVSIUL[slot]->MSCR[130] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[130]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI0_SOUT*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_1_CH[8]_X*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D13*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_OBE_MASK|0x7U; /*ADC0_MA[0]*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[27]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_P5*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[18] = 0x4U; /*EIRQ[2]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[51] = 0x5U; /*eMIOS_0_CH[3]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[88] = 0x4U; /*eMIOS_1_CH[8]_X*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[165] = 0x4U; /*FXIO_D13*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[231] = 0x1U; /*LPSPI0_SOUT*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[361] = 0x1U; /*LPUART1_CTS*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[130] = (prvVSIUL[slot]->MSCR[130])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN3)\
    {\
      prvVSIUL[slot]->MSCR[131] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[131]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_OBE_MASK|0x1U; /*CAN4_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D6*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPUART2_RTS*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_OBE_MASK|0x7U; /*CMP0_OUT*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[19] = 0x4U; /*EIRQ[3]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[67] = 0x4U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x6U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[192] = 0x1U; /*LPUART5_RX*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[350] = 0x1U; /*TRGMUX_IN6*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[131] = (prvVSIUL[slot]->MSCR[131])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN4)\
    {\
      prvVSIUL[slot]->MSCR[132] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[132]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI0_PCS0*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI1_PCS1*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[18]_Y*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[20] = 0x4U; /*EIRQ[4]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[66] = 0x2U; /*eMIOS_0_CH[18]_Y*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[84] = 0x4U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[158] = 0x1U; /*FXIO_D6*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[221] = 0x5U; /*LPSPI0_PCS0*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[233] = 0x5U; /*LPSPI1_PCS1*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[132] = (prvVSIUL[slot]->MSCR[132])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN5)\
    {\
      prvVSIUL[slot]->MSCR[133] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[133]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[32]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[21] = 0x4U; /*EIRQ[5]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[67] = 0x1U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[85] = 0x4U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x1U; /*FXIO_D7*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[133] = (prvVSIUL[slot]->MSCR[133])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN6)\
    {\
      prvVSIUL[slot]->MSCR[134] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[134]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI0_PCS2*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPUART1_RTS*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D12*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_OBE_MASK|0x7U; /*ADC0_MA[1]*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_P6*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[29]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[22] = 0x4U; /*EIRQ[6]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[94] = 0x5U; /*eMIOS_1_CH[14]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[164] = 0x4U; /*FXIO_D12*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[223] = 0x1U; /*LPSPI0_PCS2*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[134] = (prvVSIUL[slot]->MSCR[134])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN7)\
    {\
      prvVSIUL[slot]->MSCR[135] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[135]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[7]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_OBE_MASK|0x6U; /*LPSPI3_SCK*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[55] = 0x2U; /*eMIOS_0_CH[7]_G*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[163] = 0x4U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[191] = 0x4U; /*LPUART4_RX*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[252] = 0x2U; /*LPSPI3_SCK*/\
      }\
      if(__t & (INP_ALT4 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[135] = (prvVSIUL[slot]->MSCR[135])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN8)\
    {\
      prvVSIUL[slot]->MSCR[136] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[136]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPSPI3_PCS1*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[6]_G*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_OBE_MASK|0x4U; /*FXIO_D12*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D8*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN3*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[23] = 0x4U; /*EIRQ[7]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[54] = 0x1U; /*eMIOS_0_CH[6]_G*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[160] = 0x5U; /*FXIO_D8*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[164] = 0x1U; /*FXIO_D12*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[249] = 0x1U; /*LPSPI3_PCS1*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[136] = (prvVSIUL[slot]->MSCR[136])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN9)\
    {\
      prvVSIUL[slot]->MSCR[137] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[137]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[7]_G*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_1_CH[13]_H*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_OBE_MASK|0x4U; /*CAN3_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin CMP0_IN0*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[24] = 0x4U; /*EIRQ[8]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[55] = 0x1U; /*eMIOS_0_CH[7]_G*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[93] = 0x5U; /*eMIOS_1_CH[13]_H*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[163] = 0x1U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[362] = 0x3U; /*LPUART2_CTS*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[137] = (prvVSIUL[slot]->MSCR[137])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN10)\
    {\
      prvVSIUL[slot]->MSCR[138] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[138]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI3_SIN*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_PCS1*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[20]_Y*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_OBE_MASK|0x5U; /*CLKOUT_STANDBY*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D4*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT4*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_P5*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[25] = 0x4U; /*EIRQ[9]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[68] = 0x2U; /*eMIOS_0_CH[20]_Y*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[156] = 0x2U; /*FXIO_D4*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[191] = 0x2U; /*LPUART4_RX*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[242] = 0x1U; /*LPSPI2_PCS1*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[253] = 0x1U; /*LPSPI3_SIN*/\
      }\
      if(__t & (INP_ALT7 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[138] = (prvVSIUL[slot]->MSCR[138])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN11)\
    {\
      prvVSIUL[slot]->MSCR[139] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[139]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_OBE_MASK|0x1U; /*LPUART4_TX*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPSPI2_PCS0*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_OBE_MASK|0x3U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[21]_Y*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D5*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT5*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[28]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC0_P6*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[26] = 0x4U; /*EIRQ[10]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[49] = 0x4U; /*eMIOS_0_CH[1]_G*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[69] = 0x2U; /*eMIOS_0_CH[21]_Y*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x1U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[241] = 0x3U; /*LPSPI2_PCS0*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[367] = 0x3U; /*LPUART4_TX*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[139] = (prvVSIUL[slot]->MSCR[139])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN12)\
    {\
      prvVSIUL[slot]->MSCR[140] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[140]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_OBE_MASK|0x1U; /*CMP0_RRT*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_OBE_MASK|0x2U; /*CAN5_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPUART2_TX*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D8*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[27] = 0x4U; /*EIRQ[11]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[85] = 0x5U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x9U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[160] = 0x1U; /*FXIO_D8*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[365] = 0x4U; /*LPUART2_TX*/\
      }\
      if(__t & (INP_ALT5 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[140] = (prvVSIUL[slot]->MSCR[140])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN13)\
    {\
      prvVSIUL[slot]->MSCR[141] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[141]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_PCS2*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPSPI2_PCS0*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S19*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[28] = 0x4U; /*EIRQ[12]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[85] = 0x3U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x5U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[241] = 0x5U; /*LPSPI2_PCS0*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[243] = 0x2U; /*LPSPI2_PCS2*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[141] = (prvVSIUL[slot]->MSCR[141])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN14)\
    {\
      prvVSIUL[slot]->MSCR[142] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[142]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_OBE_MASK|0x1U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_OBE_MASK|0x4U; /*LPUART5_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[30]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[4] = 0x1U; /*CAN4_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[29] = 0x4U; /*EIRQ[13]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[67] = 0x3U; /*eMIOS_0_CH[19]_Y*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[159] = 0x5U; /*FXIO_D7*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[368] = 0x2U; /*LPUART5_TX*/\
      }\
      if(__t & (INP_ALT6 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[142] = (prvVSIUL[slot]->MSCR[142])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN15)\
    {\
      prvVSIUL[slot]->MSCR[143] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[143]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_OBE_MASK|0x1U; /*FCCU_ERR0*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_SCK*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[22]_X*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_OBE_MASK|0x5U; /*CMP1_RRT*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D2*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT6*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_P3*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[30] = 0x4U; /*EIRQ[14]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[70] = 0x1U; /*eMIOS_0_CH[22]_X*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[148] = 0x2U; /*FCCU_ERR_IN0*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[154] = 0x1U; /*FXIO_D2*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[190] = 0x1U; /*LPUART3_RX*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[245] = 0x1U; /*LPSPI2_SCK*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[361] = 0x3U; /*LPUART1_CTS*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[143] = (prvVSIUL[slot]->MSCR[143])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN16)\
    {\
      prvVSIUL[slot]->MSCR[144] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[144]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x1U; /*FCCU_ERR1*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x2U; /*LPUART3_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x3U; /*LPSPI2_SIN*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x4U; /*eMIOS_0_CH[23]_X*/\
      }\
      if(__t & OUT_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x5U; /*LPUART1_RTS*/\
      }\
      if(__t & OUT_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x6U; /*FXIO_D3*/\
      }\
      if(__t & OUT_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_OBE_MASK|0x7U; /*TRGMUX_OUT7*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC0_P4*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin WKPU[19]*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[31] = 0x4U; /*EIRQ[15]*/\
      }\
      if(__t & INP_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[71] = 0x2U; /*eMIOS_0_CH[23]_X*/\
      }\
      if(__t & INP_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[149] = 0x2U; /*FCCU_ERR_IN1*/\
      }\
      if(__t & INP_ALT5)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[155] = 0x2U; /*FXIO_D3*/\
      }\
      if(__t & INP_ALT6)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[246] = 0x1U; /*LPSPI2_SIN*/\
      }\
      if(__t & INP_ALT7)\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[366] = 0x3U; /*LPUART3_TX*/\
      }\
      if(__t & (INP_ALT8 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[144] = (prvVSIUL[slot]->MSCR[144])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN17)\
    {\
      prvVSIUL[slot]->MSCR[145] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[145] = (prvVSIUL[slot]->MSCR[145])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[145]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[145] = (prvVSIUL[slot]->MSCR[145])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin ADC1_S22*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[145] = (prvVSIUL[slot]->MSCR[145])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0x4U; /*FXIO_D5*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[145] = (prvVSIUL[slot]->MSCR[145])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN18)\
    {\
      prvVSIUL[slot]->MSCR[146] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[146] = (prvVSIUL[slot]->MSCR[146])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[146]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[146] = (prvVSIUL[slot]->MSCR[146])|SIUL2_MSCR_OBE_MASK|0x3U; /*FXIO_D4*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[55]*/\
      }\
      if(__t & INP_ALT1)\
      {\
      /*Direct pin ADC1_S23*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[146] = (prvVSIUL[slot]->MSCR[146])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[156] = 0x4U; /*FXIO_D4*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[146] = (prvVSIUL[slot]->MSCR[146])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN19)\
    {\
      prvVSIUL[slot]->MSCR[147] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[147] = (prvVSIUL[slot]->MSCR[147])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[147]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[147] = (prvVSIUL[slot]->MSCR[147])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_0_CH[22]_X*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[147] = (prvVSIUL[slot]->MSCR[147])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[70] = 0x3U; /*eMIOS_0_CH[22]_X*/\
      }\
      if(__t & (INP_ALT1 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[147] = (prvVSIUL[slot]->MSCR[147])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN20)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN21)\
    {\
      prvVSIUL[slot]->MSCR[149] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[149] = (prvVSIUL[slot]->MSCR[149])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[149]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[149] = (prvVSIUL[slot]->MSCR[149])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[56]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[149] = (prvVSIUL[slot]->MSCR[149])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[81] = 0x2U; /*eMIOS_1_CH[1]_H*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[149] = (prvVSIUL[slot]->MSCR[149])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN22)\
    {\
      prvVSIUL[slot]->MSCR[150] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[150] = (prvVSIUL[slot]->MSCR[150])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[150]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[150] = (prvVSIUL[slot]->MSCR[150])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[150] = (prvVSIUL[slot]->MSCR[150])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[82] = 0x3U; /*eMIOS_1_CH[2]_H*/\
      }\
      if(__t & (INP_ALT1 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[150] = (prvVSIUL[slot]->MSCR[150])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN23)\
    {\
      prvVSIUL[slot]->MSCR[151] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[151] = (prvVSIUL[slot]->MSCR[151])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[151]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[151] = (prvVSIUL[slot]->MSCR[151])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[57]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[151] = (prvVSIUL[slot]->MSCR[151])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[83] = 0x2U; /*eMIOS_1_CH[3]_H*/\
      }\
      if(__t & (INP_ALT2 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[151] = (prvVSIUL[slot]->MSCR[151])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN24)\
    {\
      prvVSIUL[slot]->MSCR[152] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[152]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & OUT_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_OBE_MASK|0x3U; /*CAN2_TX*/\
      }\
      if(__t & OUT_ALT3)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_OBE_MASK|0x5U; /*FXIO_D5*/\
      }\
      if(__t & OUT_ALT4)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_OBE_MASK|0x7U; /*FXIO_D11*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[84] = 0x3U; /*eMIOS_1_CH[4]_H*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[157] = 0xaU; /*FXIO_D5*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[163] = 0x6U; /*FXIO_D11*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[152] = (prvVSIUL[slot]->MSCR[152])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN25)\
    {\
      prvVSIUL[slot]->MSCR[153] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[153] = (prvVSIUL[slot]->MSCR[153])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[153]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[153] = (prvVSIUL[slot]->MSCR[153])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
      /*Direct pin WKPU[58]*/\
      }\
      if(__t & INP_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[153] = (prvVSIUL[slot]->MSCR[153])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[2] = 0x3U; /*CAN2_RX*/\
      }\
      if(__t & INP_ALT2)\
      {\
        prvVSIUL[slot]->MSCR[153] = (prvVSIUL[slot]->MSCR[153])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[85] = 0x2U; /*eMIOS_1_CH[5]_H*/\
      }\
      if(__t & (INP_ALT3 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[153] = (prvVSIUL[slot]->MSCR[153])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN26)\
    {\
      prvVSIUL[slot]->MSCR[154] = cfg; /*electrical characteristics*/\
      if(__t & OUT_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[154] = (prvVSIUL[slot]->MSCR[154])|SIUL2_MSCR_OBE_MASK|0x0U; /*GPIO[154]*/\
      }\
      if(__t & OUT_ALT1)\
      {\
        prvVSIUL[slot]->MSCR[154] = (prvVSIUL[slot]->MSCR[154])|SIUL2_MSCR_OBE_MASK|0x2U; /*eMIOS_1_CH[6]_H*/\
      }\
      if(__t & INP_ALT0)\
      {\
        prvVSIUL[slot]->MSCR[154] = (prvVSIUL[slot]->MSCR[154])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable*/\
        prvVSIUL[slot]->IMCR[86] = 0x3U; /*eMIOS_1_CH[6]_H*/\
      }\
      if(__t & (INP_ALT1 | INP_GPIO))\
      {\
        prvVSIUL[slot]->MSCR[154] = (prvVSIUL[slot]->MSCR[154])|SIUL2_MSCR_IBE_MASK; /*Input buffer enable only*/\
      }\
    }\
    if((pins) & PIN27)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN28)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN29)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN30)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
    if((pins) & PIN31)\
    {\
      /*output functionality does not exist*/\
      /*input functionality does not exist*/\
    }\
  }\
}while(0)

#endif /* __SIUL_S32K312_H */
