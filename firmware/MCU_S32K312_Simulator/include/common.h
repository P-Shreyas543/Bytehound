/******************************************************************************
 * (c) Copyright 2018-2020, NXP Semiconductor Inc.
 * ALL RIGHTS RESERVED.
 ***************************************************************************//*!
 * @file      common.h
 * @brief     Header file.
 ******************************************************************************/
#ifndef __COMMON_H
#define __COMMON_H

/******************************************************************************
 * Bare metal drivers macros and defines                                      *
 ******************************************************************************/
#ifndef NULL
  #define NULL    (void*)0
#endif
#ifndef TRUE
  #define TRUE    1
#endif
#ifndef FALSE
  #define FALSE   0
#endif

/******************************************************************************
 * Function and variable placement defines                                    *
 ******************************************************************************/
#define __tcmfunc   __attribute__((section(".itcm.$func"), noinline))
#if defined (__GNUC__)
  #define __ramfunc   __attribute__((section(".nram.$func"), noinline))
#endif
#define __dromfunc  __attribute__((section(".drom.$func"), noinline))
#define __dromdata  __attribute__((section(".drom.$data")))
#define __tcmdata   __attribute__((section(".dtcm.$data")))
#define __tcmbss    __attribute__((section(".dtcm.$bss" )))
#define __sramdata  __attribute__((section(".sram.$data")))
#define __srambss   __attribute__((section(".sram.$bss" )))

/******************************************************************************
* Priority level definition
*
*//*! @addtogroup irq_prilvl
* @{
*******************************************************************************/
#define IRQ_LVL0  (uint8_t)0x00 ///< Priority level 0 (highest priority)
#define IRQ_LVL1  (uint8_t)0x01 ///< Priority level 1
#define IRQ_LVL2  (uint8_t)0x02 ///< Priority level 2
#define IRQ_LVL3  (uint8_t)0x03 ///< Priority level 3
#define IRQ_LVL4  (uint8_t)0x04 ///< Priority level 4
#define IRQ_LVL5  (uint8_t)0x05 ///< Priority level 5
#define IRQ_LVL6  (uint8_t)0x06 ///< Priority level 6
#define IRQ_LVL7  (uint8_t)0x07 ///< Priority level 7
#define IRQ_LVL8  (uint8_t)0x08 ///< Priority level 8
#define IRQ_LVL9  (uint8_t)0x09 ///< Priority level 9
#define IRQ_LVL10 (uint8_t)0x0a ///< Priority level 10
#define IRQ_LVL11 (uint8_t)0x0b ///< Priority level 11
#define IRQ_LVL12 (uint8_t)0x0c ///< Priority level 12
#define IRQ_LVL13 (uint8_t)0x0d ///< Priority level 13
#define IRQ_LVL14 (uint8_t)0x0e ///< Priority level 14
#define IRQ_LVL15 (uint8_t)0x0f ///< Priority level 15 (lowest priority)
/*! @} End of irq_prilvl                                                      */

/******************************************************************************
 * List of the basic configuration structure macros
 *
 *//*! @addtogroup config_struct_macros
 * @{
 ******************************************************************************/
/***************************************************************************//*!
 * @brief   Sets register field in peripheral configuration structure.
 * @details This macro sets register field <c>mask</c> in the peripheral
 *          configuration structure.
 * @param   mask  Register field to be set.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define SET(mask)   (mask)

/***************************************************************************//*!
 * @brief   Clears register field in peripheral configuration structure.
 * @details This macro clears register field <c>mask</c> in the peripheral
 *          configuration structure.
 * @param   mask  Register field to be cleared.
 * @note    Implemented as a macro.
 ******************************************************************************/
#define CLR(mask)   0
/*! @} End of config_struct_macros                                            */

/******************************************************************************
 * Include common header file                                                 *
 ******************************************************************************/
#include "version.h"      /* Bare-metal drivers version constants             */
#include "typedefs.h"     /* Basic data types and conversion macros           */
#include "appconfig.h"    /* User configuration definitions and structures    */
#include "defconfig.h"    /* Default configuration definitions                */

#include "S32K312.h"

#if defined (__ARM_FP)
  #include "armcm7_sp.h"
#else
  #include "armcm7.h"
#endif

#endif /* __COMMON_H */
