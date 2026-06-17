/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      siul.h
 * @brief     System Integration Unit Lite2 (SIUL) driver header file.
 */
#ifndef __SIUL_H
#define __SIUL_H

extern volatile SIUL2_Type * const prvVSIUL[];

#include "siul_private.h"    /* include private definitions                   */
#include "siul_s32k312.h"

/******************************************************************************
 * SIUL driver configuration
 *
 *//*! @addtogroup siul_drv
 * @{
 * @details SIUL driver includes basic functions and macros writing control registers through slot 0 (@ref VWRAP_SIUL0). By default, all SIUL control 
 * registers are accessible by basic functions. In order to support freedom from interference, user can use @ref vwrap_drv to map SIUL control registers
 * to different slots. Accessing SIUL control registers through different slot than zero is possible using "virtual" functions and macros.
 * 
 * List of basic functions and macros and their virtual equivalents:
 * |Basic function and macro         |Virtual function and macro <SUP>1</SUP>|Description                                                                  |
 * |:-------------------------------:|:-------------------------------------:|:---------------------------------------------------------------------------:|
 * |@ref SIUL_ClrPin                 |VSIUL_ClrPin(slot,...)                 |Clear state of pin.                                                          |
 * |@ref SIUL_DisableOutBuff         |VSIUL_DisableOutBuff(slot,...)         |Disable output buffer of pin.                                                |    
 * |@ref SIUL_DisableResetInputFilter|VSIUL_DisableResetInputFilter(slot,...)|Disable reset input filter.                                                  |                
 * |@ref SIUL_EnableDma              |VSIUL_EnableDma(slot,...)              |Enables DMA requests of the SIUL module.                                     |                
 * |@ref SIUL_EnableIrq              |VSIUL_EnableIrq(slot,...)              |Enables interrupt requests of the SIUL module.                               |                      
 * |@ref SIUL_EnableOutBuff          |VSIUL_EnableOutBuff(slot,...)          |Enable output buffer of pin.                                                 |    
 * |@ref SIUL_EnableResetInputFilter |VSIUL_EnableResetInputFilter(slot,...) |Enable reset input filter.                                                   |              
 * |@ref SIUL_GetGrpVal              |VSIUL_GetGrpVal(slot,...)              |Returns state of pin group.                                                  |  
 * |@ref SIUL_GetPin                 |VSIUL_GetPin(slot,...)                 |Returns state of pin.                                                        |
 * |@ref SIUL_Init                   |VSIUL_Init(slot,...)                   |Installs callback function for interrupt vector depended on SIUL module.     |                                                    
 * |@ref SIUL_InstallCallback        |VSIUL_InstallCallback(slot,...)        |SIUL2 modul initialization.                                                  |  
 * |@ref SIUL_SetGlitchFilterPresc   |VSIUL_SetGlitchFilterPresc(slot,...)   |Sets glitch filter prescaler.                                                |              
 * |@ref SIUL_SetGrpMaskedVal        |VSIUL_SetGrpMaskedVal(slot,...)        |Set state of pin group by masked value.                                      |              
 * |@ref SIUL_SetGrpVal              |VSIUL_SetGrpVal(slot,...)              |Set state of pin group by value.                                             |        
 * |@ref SIUL_SetPin                 |VSIUL_SetPin(slot,...)                 |Set state of pin.                                                            |
 * |@ref SIUL_SetPinVal              |VSIUL_SetPinVal(slot,...)              |Set state of pin by value.                                                   |  
 * |@ref SIUL_SetTrgmuxPath          |VSIUL_SetTrgmuxPath(slot,...)          |Selects peripheral inputs that will be routed from predefined TRGMUX outputs.|                                                    
 * |@ref SIUL_TglPin                 |VSIUL_TglPin(slot,...)                 |Toggle state of pin.                                                         |
 * @note Virtual function and macros start with "V" character and their first input argument is always slot number (refer to @ref vwrap_drv). The remaining 
 * input arguments are identical with basic equivalent.      
 ******************************************************************************/
/*! @} End of siul_drv                                                        */

/******************************************************************************
 * Configuration structure definitions                                        *
 ******************************************************************************/
typedef uint32_t  tPORT;

/******************************************************************************
* SIUL ports
*
*//*! @addtogroup siul_ports
* @{
*******************************************************************************/
#define PTA     (uint16_t)(1U << 0) ///< Port PTA
#define PTB     (uint16_t)(1U << 1) ///< Port PTB
#define PTC     (uint16_t)(1U << 2) ///< Port PTC
#define PTD     (uint16_t)(1U << 3) ///< Port PTD
#define PTE     (uint16_t)(1U << 4) ///< Port PTE
#define PTF     (uint16_t)(1U << 5) ///< Port PTF
#define PTG     (uint16_t)(1U << 6) ///< Port PTG
#define PTH     (uint16_t)(1U << 7) ///< Port PTH
#define PTALL   (uint16_t)~0U       ///< All ports
/*! @} End of siul_ports                                                     */

/******************************************************************************
* SIUL pins
*
*//*! @addtogroup siul_pins
* @{
*******************************************************************************/
#define PIN0    (uint32_t)(1UL << 0)  ///< Pin 0
#define PIN1    (uint32_t)(1UL << 1)  ///< Pin 1
#define PIN2    (uint32_t)(1UL << 2)  ///< Pin 2
#define PIN3    (uint32_t)(1UL << 3)  ///< Pin 3
#define PIN4    (uint32_t)(1UL << 4)  ///< Pin 4
#define PIN5    (uint32_t)(1UL << 5)  ///< Pin 5
#define PIN6    (uint32_t)(1UL << 6)  ///< Pin 6
#define PIN7    (uint32_t)(1UL << 7)  ///< Pin 7
#define PIN8    (uint32_t)(1UL << 8)  ///< Pin 8
#define PIN9    (uint32_t)(1UL << 9)  ///< Pin 9
#define PIN10   (uint32_t)(1UL << 10) ///< Pin 10
#define PIN11   (uint32_t)(1UL << 11) ///< Pin 11
#define PIN12   (uint32_t)(1UL << 12) ///< Pin 12
#define PIN13   (uint32_t)(1UL << 13) ///< Pin 13
#define PIN14   (uint32_t)(1UL << 14) ///< Pin 14
#define PIN15   (uint32_t)(1UL << 15) ///< Pin 15
#define PIN16   (uint32_t)(1UL << 16) ///< Pin 16
#define PIN17   (uint32_t)(1UL << 17) ///< Pin 17
#define PIN18   (uint32_t)(1UL << 18) ///< Pin 18
#define PIN19   (uint32_t)(1UL << 19) ///< Pin 19
#define PIN20   (uint32_t)(1UL << 20) ///< Pin 20
#define PIN21   (uint32_t)(1UL << 21) ///< Pin 21
#define PIN22   (uint32_t)(1UL << 22) ///< Pin 22
#define PIN23   (uint32_t)(1UL << 23) ///< Pin 23
#define PIN24   (uint32_t)(1UL << 24) ///< Pin 24
#define PIN25   (uint32_t)(1UL << 25) ///< Pin 25
#define PIN26   (uint32_t)(1UL << 26) ///< Pin 26
#define PIN27   (uint32_t)(1UL << 27) ///< Pin 27
#define PIN28   (uint32_t)(1UL << 28) ///< Pin 28
#define PIN29   (uint32_t)(1UL << 29) ///< Pin 29
#define PIN30   (uint32_t)(1UL << 30) ///< Pin 30
#define PIN31   (uint32_t)(1UL << 31) ///< Pin 31
#define PINALL  (uint32_t)~0UL        ///< All pins
/*! @} End of siul_pins                                                      */

/******************************************************************************
* SIUL pins
*
*//*! @addtogroup siul_groups
* @{
*******************************************************************************/
#define PIN_GRP0  (uint32_t)(1UL << 0)  ///< Group 0
#define PIN_GRP1  (uint32_t)(1UL << 1)  ///< Group 1
#define PIN_GRP2  (uint32_t)(1UL << 2)  ///< Group 2
#define PIN_GRP3  (uint32_t)(1UL << 3)  ///< Group 3
#define PIN_GRP4  (uint32_t)(1UL << 4)  ///< Group 4
#define PIN_GRP5  (uint32_t)(1UL << 5)  ///< Group 5
#define PIN_GRP6  (uint32_t)(1UL << 6)  ///< Group 6
#define PIN_GRP7  (uint32_t)(1UL << 7)  ///< Group 7
#define PIN_GRP8  (uint32_t)(1UL << 8)  ///< Group 8
#define PIN_GRP9  (uint32_t)(1UL << 9)  ///< Group 9
#define PIN_GRP10 (uint32_t)(1UL << 10) ///< Group 10
#define PIN_GRP11 (uint32_t)(1UL << 11) ///< Group 11
#define PIN_GRP12 (uint32_t)(1UL << 12) ///< Group 12
#define PIN_GRP13 (uint32_t)(1UL << 13) ///< Group 13
#define PIN_GRP14 (uint32_t)(1UL << 14) ///< Group 14
#define PIN_GRP15 (uint32_t)(1UL << 15) ///< Group 15
/*! @} End of siul_groups                                                     */

/******************************************************************************
* SIUL irq groups
*
*//*! @addtogroup siul_irq_groups
* @{
*******************************************************************************/
#define IRQ_GRP0  0 ///< External interrupt vector 0 (interrupts EIRQ[ 0]–EIRQ[ 8])
#define IRQ_GRP1  1 ///< External interrupt vector 1 (interrupts EIRQ[ 9]–EIRQ[15])
#define IRQ_GRP2  2 ///< External interrupt vector 2 (interrupts EIRQ[16]–EIRQ[23])
#define IRQ_GRP3  3 ///< External interrupt vector 3 (interrupts EIRQ[24]–EIRQ[31])
/*! @} End of siul_irq_groups                                                 */

/******************************************************************************
* SIUL interrupt requests
*
*//*! @addtogroup siul_irq_req
* @{
*******************************************************************************/
#define IRQ_REQ0  (uint32_t)(1UL << 0)  ///< SIUL interrupt request 0  (EIRQ[ 0])
#define IRQ_REQ1  (uint32_t)(1UL << 1)  ///< SIUL interrupt request 1  (EIRQ[ 1])
#define IRQ_REQ2  (uint32_t)(1UL << 2)  ///< SIUL interrupt request 2  (EIRQ[ 2])
#define IRQ_REQ3  (uint32_t)(1UL << 3)  ///< SIUL interrupt request 3  (EIRQ[ 3])
#define IRQ_REQ4  (uint32_t)(1UL << 4)  ///< SIUL interrupt request 4  (EIRQ[ 4])
#define IRQ_REQ5  (uint32_t)(1UL << 5)  ///< SIUL interrupt request 5  (EIRQ[ 5])
#define IRQ_REQ6  (uint32_t)(1UL << 6)  ///< SIUL interrupt request 6  (EIRQ[ 6])
#define IRQ_REQ7  (uint32_t)(1UL << 7)  ///< SIUL interrupt request 7  (EIRQ[ 7])
#define IRQ_REQ8  (uint32_t)(1UL << 8)  ///< SIUL interrupt request 8  (EIRQ[ 8])
#define IRQ_REQ9  (uint32_t)(1UL << 9)  ///< SIUL interrupt request 9  (EIRQ[ 9])
#define IRQ_REQ10 (uint32_t)(1UL << 10) ///< SIUL interrupt request 10 (EIRQ[10])
#define IRQ_REQ11 (uint32_t)(1UL << 11) ///< SIUL interrupt request 11 (EIRQ[11])
#define IRQ_REQ12 (uint32_t)(1UL << 12) ///< SIUL interrupt request 12 (EIRQ[12])
#define IRQ_REQ13 (uint32_t)(1UL << 13) ///< SIUL interrupt request 13 (EIRQ[13])
#define IRQ_REQ14 (uint32_t)(1UL << 14) ///< SIUL interrupt request 14 (EIRQ[14])
#define IRQ_REQ15 (uint32_t)(1UL << 15) ///< SIUL interrupt request 15 (EIRQ[15])
#define IRQ_REQ16 (uint32_t)(1UL << 16) ///< SIUL interrupt request 16 (EIRQ[16])
#define IRQ_REQ17 (uint32_t)(1UL << 17) ///< SIUL interrupt request 17 (EIRQ[17])
#define IRQ_REQ18 (uint32_t)(1UL << 18) ///< SIUL interrupt request 18 (EIRQ[18])
#define IRQ_REQ19 (uint32_t)(1UL << 19) ///< SIUL interrupt request 19 (EIRQ[19])
#define IRQ_REQ20 (uint32_t)(1UL << 20) ///< SIUL interrupt request 20 (EIRQ[20])
#define IRQ_REQ21 (uint32_t)(1UL << 21) ///< SIUL interrupt request 21 (EIRQ[21])
#define IRQ_REQ22 (uint32_t)(1UL << 22) ///< SIUL interrupt request 22 (EIRQ[22])
#define IRQ_REQ23 (uint32_t)(1UL << 23) ///< SIUL interrupt request 23 (EIRQ[23])
#define IRQ_REQ24 (uint32_t)(1UL << 24) ///< SIUL interrupt request 24 (EIRQ[24])
#define IRQ_REQ25 (uint32_t)(1UL << 25) ///< SIUL interrupt request 25 (EIRQ[25])
#define IRQ_REQ26 (uint32_t)(1UL << 26) ///< SIUL interrupt request 26 (EIRQ[26])
#define IRQ_REQ27 (uint32_t)(1UL << 27) ///< SIUL interrupt request 27 (EIRQ[27])
#define IRQ_REQ28 (uint32_t)(1UL << 28) ///< SIUL interrupt request 28 (EIRQ[28])
#define IRQ_REQ29 (uint32_t)(1UL << 29) ///< SIUL interrupt request 29 (EIRQ[29])
#define IRQ_REQ30 (uint32_t)(1UL << 30) ///< SIUL interrupt request 30 (EIRQ[30])
#define IRQ_REQ31 (uint32_t)(1UL << 31) ///< SIUL interrupt request 31 (EIRQ[31])
/*! @} siul_irq_req                                                           */

/******************************************************************************
* SIUL DMA requests
*
*//*! @addtogroup siul_dma_req
* @{
*******************************************************************************/
#define DMA_REQ0  (uint32_t)(1UL << 0)  ///< SIUL DMA request 0  (EIRQ[ 0])
#define DMA_REQ1  (uint32_t)(1UL << 1)  ///< SIUL DMA request 1  (EIRQ[ 1])
#define DMA_REQ2  (uint32_t)(1UL << 2)  ///< SIUL DMA request 2  (EIRQ[ 2])
#define DMA_REQ3  (uint32_t)(1UL << 3)  ///< SIUL DMA request 3  (EIRQ[ 3])
#define DMA_REQ4  (uint32_t)(1UL << 4)  ///< SIUL DMA request 4  (EIRQ[ 4])
#define DMA_REQ5  (uint32_t)(1UL << 5)  ///< SIUL DMA request 5  (EIRQ[ 5])
#define DMA_REQ6  (uint32_t)(1UL << 6)  ///< SIUL DMA request 6  (EIRQ[ 6])
#define DMA_REQ7  (uint32_t)(1UL << 7)  ///< SIUL DMA request 7  (EIRQ[ 7])
#define DMA_REQ8  (uint32_t)(1UL << 8)  ///< SIUL DMA request 8  (EIRQ[ 8])
#define DMA_REQ9  (uint32_t)(1UL << 9)  ///< SIUL DMA request 9  (EIRQ[ 9])
#define DMA_REQ10 (uint32_t)(1UL << 10) ///< SIUL DMA request 10 (EIRQ[10])
#define DMA_REQ11 (uint32_t)(1UL << 11) ///< SIUL DMA request 11 (EIRQ[11])
#define DMA_REQ12 (uint32_t)(1UL << 12) ///< SIUL DMA request 12 (EIRQ[12])
#define DMA_REQ13 (uint32_t)(1UL << 13) ///< SIUL DMA request 13 (EIRQ[13])
#define DMA_REQ14 (uint32_t)(1UL << 14) ///< SIUL DMA request 14 (EIRQ[14])
#define DMA_REQ15 (uint32_t)(1UL << 15) ///< SIUL DMA request 15 (EIRQ[15])
#define DMA_REQ16 (uint32_t)(1UL << 16) ///< SIUL DMA request 16 (EIRQ[16])
#define DMA_REQ17 (uint32_t)(1UL << 17) ///< SIUL DMA request 17 (EIRQ[17])
#define DMA_REQ18 (uint32_t)(1UL << 18) ///< SIUL DMA request 18 (EIRQ[18])
#define DMA_REQ19 (uint32_t)(1UL << 19) ///< SIUL DMA request 19 (EIRQ[19])
#define DMA_REQ20 (uint32_t)(1UL << 20) ///< SIUL DMA request 20 (EIRQ[20])
#define DMA_REQ21 (uint32_t)(1UL << 21) ///< SIUL DMA request 21 (EIRQ[21])
#define DMA_REQ22 (uint32_t)(1UL << 22) ///< SIUL DMA request 22 (EIRQ[22])
#define DMA_REQ23 (uint32_t)(1UL << 23) ///< SIUL DMA request 23 (EIRQ[23])
#define DMA_REQ24 (uint32_t)(1UL << 24) ///< SIUL DMA request 24 (EIRQ[24])
#define DMA_REQ25 (uint32_t)(1UL << 25) ///< SIUL DMA request 25 (EIRQ[25])
#define DMA_REQ26 (uint32_t)(1UL << 26) ///< SIUL DMA request 26 (EIRQ[26])
#define DMA_REQ27 (uint32_t)(1UL << 27) ///< SIUL DMA request 27 (EIRQ[27])
#define DMA_REQ28 (uint32_t)(1UL << 28) ///< SIUL DMA request 28 (EIRQ[28])
#define DMA_REQ29 (uint32_t)(1UL << 29) ///< SIUL DMA request 29 (EIRQ[29])
#define DMA_REQ30 (uint32_t)(1UL << 30) ///< SIUL DMA request 30 (EIRQ[30])
#define DMA_REQ31 (uint32_t)(1UL << 31) ///< SIUL DMA request 31 (EIRQ[31])
/*! @} siul_dma_req                                                           */

/******************************************************************************
* SIUL input alternatives.
*
*//*! @addtogroup siul_inputs
* @{
*******************************************************************************/
#define INP_NONE   0UL                   ///< Pin not used as input (input buffer disabled)
#define INP_ALT0   (uint32_t)(1UL << 0)  ///< Input alternative 0 (chip specific)
#define INP_ALT1   (uint32_t)(1UL << 1)  ///< Input alternative 1 (chip specific)
#define INP_ALT2   (uint32_t)(1UL << 2)  ///< Input alternative 2 (chip specific)
#define INP_ALT3   (uint32_t)(1UL << 3)  ///< Input alternative 3 (chip specific)
#define INP_ALT4   (uint32_t)(1UL << 4)  ///< Input alternative 4 (chip specific)
#define INP_ALT5   (uint32_t)(1UL << 5)  ///< Input alternative 5 (chip specific)
#define INP_ALT6   (uint32_t)(1UL << 6)  ///< Input alternative 6 (chip specific)
#define INP_ALT7   (uint32_t)(1UL << 7)  ///< Input alternative 7 (chip specific)
#define INP_ALT8   (uint32_t)(1UL << 8)  ///< Input alternative 8 (chip specific)
#define INP_ALT9   (uint32_t)(1UL << 9)  ///< Input alternative 9 (chip specific)
#define INP_ALT10  (uint32_t)(1UL << 10) ///< Input alternative 10 (chip specific)
#define INP_ALT11  (uint32_t)(1UL << 11) ///< Input alternative 11 (chip specific)
#define INP_ALT12  (uint32_t)(1UL << 12) ///< Input alternative 12 (chip specific)
#define INP_GPIO   (uint32_t)(1UL << 13) ///< Input alternative supported by drivers (GPIO)
#define INP_ALTALL (uint32_t)0x3FFFUL    ///< All input alternatives 
/*! @} End of siul_inputs                                                     */

/******************************************************************************
* SIUL output port alternatives.
*
*//*! @addtogroup siul_outputs
* @{
*******************************************************************************/
#define OUT_NONE   0UL                   ///< Pin not used as output (output buffer disabled)
#define OUT_ALT0   (uint32_t)(1UL << 16) ///< Output alternative 0 (GPIO)
#define OUT_ALT1   (uint32_t)(1UL << 17) ///< Output alternative 1 (chip specific)
#define OUT_ALT2   (uint32_t)(1UL << 18) ///< Output alternative 2 (chip specific)
#define OUT_ALT3   (uint32_t)(1UL << 19) ///< Output alternative 3 (chip specific)
#define OUT_ALT4   (uint32_t)(1UL << 20) ///< Output alternative 4 (chip specific)
#define OUT_ALT5   (uint32_t)(1UL << 21) ///< Output alternative 5 (chip specific)
#define OUT_ALT6   (uint32_t)(1UL << 22) ///< Output alternative 6 (chip specific)
#define OUT_ALT7   (uint32_t)(1UL << 23) ///< Output alternative 7 (chip specific)
#define OUT_GPIO   OUT_ALT0              ///< Output alternative 0 (GPIO)
#define OUT_ALTALL (uint32_t)0xFF0000UL  ///< All output alternatives 
/*! @} End of siul_outputs                                                    */

/******************************************************************************
* SIUL list of peripheral inputs that will be routed from predefined TRGMUX outputs.
*
*//*! @addtogroup siul_periph_inputs_from_trgmux_outputs
* @{
*******************************************************************************/
#define SIUL_eMIOS0CH1  (uint32_t)(1UL <<  0) ///< eMIOS0 CH1 routed from TRGMUX_INT_OUT32
#define SIUL_eMIOS0CH2  (uint32_t)(1UL <<  1) ///< eMIOS0 CH2 routed from TRGMUX_INT_OUT33
#define SIUL_eMIOS0CH3  (uint32_t)(1UL <<  2) ///< eMIOS0 CH3 routed from TRGMUX_INT_OUT34
#define SIUL_eMIOS0CH4  (uint32_t)(1UL <<  3) ///< eMIOS0 CH4 routed from TRGMUX_INT_OUT35
#define SIUL_eMIOS0CH5  (uint32_t)(1UL <<  4) ///< eMIOS0 CH5 routed from TRGMUX_INT_OUT36
#define SIUL_eMIOS0CH6  (uint32_t)(1UL <<  5) ///< eMIOS0 CH6 routed from TRGMUX_INT_OUT37
#define SIUL_eMIOS0CH7  (uint32_t)(1UL <<  6) ///< eMIOS0 CH7 routed from TRGMUX_INT_OUT38
#define SIUL_eMIOS0CH9  (uint32_t)(1UL <<  7) ///< eMIOS0 CH9 routed from TRGMUX_INT_OUT39
#define SIUL_eMIOS0CH10 (uint32_t)(1UL <<  8) ///< eMIOS0 CH10 routed from TRGMUX_INT_OUT40
#define SIUL_eMIOS0CH11 (uint32_t)(1UL <<  9) ///< eMIOS0 CH11 routed from TRGMUX_INT_OUT41
#define SIUL_eMIOS0CH12 (uint32_t)(1UL << 10) ///< eMIOS0 CH12 routed from TRGMUX_INT_OUT42
#define SIUL_eMIOS0CH13 (uint32_t)(1UL << 11) ///< eMIOS0 CH13 routed from TRGMUX_INT_OUT43
#define SIUL_eMIOS0CH14 (uint32_t)(1UL << 12) ///< eMIOS0 CH14 routed from TRGMUX_INT_OUT44
#define SIUL_eMIOS0CH15 (uint32_t)(1UL << 13) ///< eMIOS0 CH15 routed from TRGMUX_INT_OUT45
#define SIUL_eMIOS1CH1  (uint32_t)(1UL << 14) ///< eMIOS1 CH1 routed from TRGMUX_INT_OUT48
#define SIUL_eMIOS1CH2  (uint32_t)(1UL << 15) ///< eMIOS1 CH2 routed from TRGMUX_INT_OUT49
#define SIUL_eMIOS1CH3  (uint32_t)(1UL << 16) ///< eMIOS1 CH3 routed from TRGMUX_INT_OUT50
#define SIUL_eMIOS1CH4  (uint32_t)(1UL << 17) ///< eMIOS1 CH4 routed from TRGMUX_INT_OUT51
#define SIUL_eMIOS1CH5  (uint32_t)(1UL << 18) ///< eMIOS1 CH5 routed from TRGMUX_INT_OUT52
#define SIUL_eMIOS1CH6  (uint32_t)(1UL << 19) ///< eMIOS1 CH6 routed from TRGMUX_INT_OUT53
#define SIUL_eMIOS1CH7  (uint32_t)(1UL << 20) ///< eMIOS1 CH7 routed from TRGMUX_INT_OUT54
#define SIUL_eMIOS1CH9  (uint32_t)(1UL << 21) ///< eMIOS1 CH9 routed from TRGMUX_INT_OUT55
#define SIUL_eMIOS1CH10 (uint32_t)(1UL << 22) ///< eMIOS1 CH10 routed from TRGMUX_INT_OUT56
#define SIUL_eMIOS1CH11 (uint32_t)(1UL << 23) ///< eMIOS1 CH11 routed from TRGMUX_INT_OUT57
#define SIUL_eMIOS1CH12 (uint32_t)(1UL << 24) ///< eMIOS1 CH12 routed from TRGMUX_INT_OUT58
#define SIUL_eMIOS1CH13 (uint32_t)(1UL << 25) ///< eMIOS1 CH13 routed from TRGMUX_INT_OUT59
#define SIUL_eMIOS1CH14 (uint32_t)(1UL << 26) ///< eMIOS1 CH14 routed from TRGMUX_INT_OUT60
#define SIUL_eMIOS1CH15 (uint32_t)(1UL << 27) ///< eMIOS1 CH15 routed from TRGMUX_INT_OUT61
/*! @} End of siul_periph_inputs_from_trgmux_outputs                          */

/******************************************************************************
* SIUL callback registered by SIUL_InstallCallback() function
*
*//*! @addtogroup siul_callback
* @{
*******************************************************************************/
/*! @brief tSIUL_CALLBACK_TYPE declaration                                    */
typedef enum
{
  REQ0_CALLBACK  =  IRQ_REQ0, ///< SIUL interrupt request 0 callback    
  REQ1_CALLBACK  =  IRQ_REQ1, ///< SIUL interrupt request 1 callback
  REQ2_CALLBACK  =  IRQ_REQ2, ///< SIUL interrupt request 2 callback
  REQ3_CALLBACK  =  IRQ_REQ3, ///< SIUL interrupt request 3 callback
  REQ4_CALLBACK  =  IRQ_REQ4, ///< SIUL interrupt request 4 callback
  REQ5_CALLBACK  =  IRQ_REQ5, ///< SIUL interrupt request 5 callback
  REQ6_CALLBACK  =  IRQ_REQ6, ///< SIUL interrupt request 6 callback
  REQ7_CALLBACK  =  IRQ_REQ7, ///< SIUL interrupt request 7 callback
  REQ8_CALLBACK  =  IRQ_REQ8, ///< SIUL interrupt request 8 callback
  REQ9_CALLBACK  =  IRQ_REQ9, ///< SIUL interrupt request 9 callback
  REQ10_CALLBACK = IRQ_REQ10, ///< SIUL interrupt request 10 callback
  REQ11_CALLBACK = IRQ_REQ11, ///< SIUL interrupt request 11 callback
  REQ12_CALLBACK = IRQ_REQ12, ///< SIUL interrupt request 12 callback
  REQ13_CALLBACK = IRQ_REQ13, ///< SIUL interrupt request 13 callback
  REQ14_CALLBACK = IRQ_REQ14, ///< SIUL interrupt request 14 callback
  REQ15_CALLBACK = IRQ_REQ15, ///< SIUL interrupt request 15 callback
  REQ16_CALLBACK = IRQ_REQ16, ///< SIUL interrupt request 16 callback
  REQ17_CALLBACK = IRQ_REQ17, ///< SIUL interrupt request 17 callback
  REQ18_CALLBACK = IRQ_REQ18, ///< SIUL interrupt request 18 callback
  REQ19_CALLBACK = IRQ_REQ19, ///< SIUL interrupt request 19 callback
  REQ20_CALLBACK = IRQ_REQ20, ///< SIUL interrupt request 20 callback
  REQ21_CALLBACK = IRQ_REQ21, ///< SIUL interrupt request 21 callback
  REQ22_CALLBACK = IRQ_REQ22, ///< SIUL interrupt request 22 callback
  REQ23_CALLBACK = IRQ_REQ23, ///< SIUL interrupt request 23 callback
  REQ24_CALLBACK = IRQ_REQ24, ///< SIUL interrupt request 24 callback
  REQ25_CALLBACK = IRQ_REQ25, ///< SIUL interrupt request 25 callback
  REQ26_CALLBACK = IRQ_REQ26, ///< SIUL interrupt request 26 callback
  REQ27_CALLBACK = IRQ_REQ27, ///< SIUL interrupt request 27 callback
  REQ28_CALLBACK = IRQ_REQ28, ///< SIUL interrupt request 28 callback
  REQ29_CALLBACK = IRQ_REQ29, ///< SIUL interrupt request 29 callback
  REQ30_CALLBACK = IRQ_REQ30, ///< SIUL interrupt request 30 callback
  REQ31_CALLBACK = IRQ_REQ31  ///< SIUL interrupt request 31 callback
} tSIUL_CALLBACK_TYPE;

/*! @brief tSIUL_CALLBACK function declaration                                */
typedef void (*tSIUL_CALLBACK)(tSIUL_CALLBACK_TYPE type);
/*! @} End of siul_callback                                                   */

/******************************************************************************
* PIN default configurations used by SIUL_Init() function
*
*//*! @addtogroup siul_pin_config
* @{
*******************************************************************************/
/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics for GPIO output mode ready for
 * controlling slow outputs such LEDs.
 * @details Configures pin(s) with the following characteristics:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_LED_MODE_CONFIG   PIN_DS_DI_PULLNO_SR_DI_PK_DI_CONFIG

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics for UART
 * @details Configures pin(s) with the following characteristics:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_UART_MODE_CONFIG   PIN_DS_DI_PULLNO_SR_DI_PK_DI_CONFIG

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics for I2C
 * @details Configures pin(s) with the following characteristics:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_I2C_MODE_CONFIG   PIN_DS_DI_PULLUP_SR_DI_PK_DI_CONFIG

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled (slowest setting) |
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_BTN_MODE_CONFIG   PIN_DS_DI_PULLUP_SR_DI_PK_DI_CONFIG

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLNO_SR_DI_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLNO_SR_DI_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Enabled  (slowest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLNO_SR_EN_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Enabled (slowest setting) |
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLNO_SR_EN_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLUP_SR_DI_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLUP_SR_DI_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled  (slowest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLUP_SR_EN_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled (slowest setting) |
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLUP_SR_EN_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLDW_SR_DI_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLDW_SR_DI_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled  (slowest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLDW_SR_EN_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Disabled                  |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled (slowest setting) |
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_DI_PULLDW_SR_EN_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ CLR(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLNO_SR_DI_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLNO_SR_DI_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Enabled  (slowest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLNO_SR_EN_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Disabled                  |
 * |Slew Rate Control                 |Enabled (slowest setting) |
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLNO_SR_EN_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|CLR(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLUP_SR_DI_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLUP_SR_DI_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled  (slowest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLUP_SR_EN_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Enabled (pull up)         |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled (slowest setting) |
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLUP_SR_EN_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|SET(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLDW_SR_DI_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Disabled (fastest setting)|
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLDW_SR_DI_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled  (slowest setting)|
 * |Pad keeping                       |Disabled                  |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLDW_SR_EN_PK_DI_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|CLR(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}

/***************************************************************************//*!
 * @brief Configures pin(s) el. characteristics.
 * @details Configures pin(s) as shown below:
 * |Feature                           |Configuration             |
 * |:--------------------------------:|:------------------------:|
 * |Drive strength                    |Enabled                   |
 * |Pull Select                       |Disabled (pull down)      |
 * |Pull Enable                       |Enabled                   |
 * |Slew Rate Control                 |Enabled (slowest setting) |
 * |Pad keeping                       |Enabled                   |
 * |Safe Mode Control                 |Disabled                  |
 * |Inverts the signal selected by SSS|Disabled (don't invert)   |
 * @showinitializer
 ******************************************************************************/
#define PIN_DS_EN_PULLDW_SR_EN_PK_EN_CONFIG                                               \
(tPORT){                                                                                  \
/* MSCR  */ SET(SIUL2_MSCR_DSE_MASK)|CLR(SIUL2_MSCR_PUS_MASK)|SET(SIUL2_MSCR_PUE_MASK)|   \
/* ....  */ SET(SIUL2_MSCR_SRE_MASK)|SET(SIUL2_MSCR_PKE_MASK)|CLR(SIUL2_MSCR_SMC_MASK)|   \
/* ....  */ CLR(SIUL2_MSCR_INV_MASK)                                                      \
}
/*! @} End of siul_pin_config                                                 */

/******************************************************************************
* SIUL2 function and macro definitions
*
*//*! @addtogroup siul_macro
* @{
*******************************************************************************/
/***************************************************************************//*!
 * @brief   SIUL2 modul initialization.
 * @details This function initializes I/O funtionality and electrical characteristics
 *          for selected pins using SIUL2 (System Integration Unit Lite2) modul.
 * @param   port  One of @ref siul_ports.
 * @param   pins  Mask of @ref siul_pins.
 * @param   fcns  One of @ref siul_outputs and mask of @ref siul_inputs.
 * @param   cfg   One of @ref siul_pin_config.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_InstallCallback, @ref SIUL_EnableIrq, @ref SIUL_EnableDma, 
 *          @ref SIUL_SetTrgmuxPath, @ref SIUL_SetGlitchFilterPresc
 ******************************************************************************/
#define SIUL_Init(port,pins,fcns,cfg)  VSIUL_Init(0,port,pins,fcns,cfg)
#define VSIUL_Init(slot,port,pins,fcns,cfg)  VSIUL_prvInit(slot,port,pins,fcns,cfg)

/***************************************************************************//*!
 * @brief   Selects peripheral inputs that will be routed from predefined TRGMUX 
 *          outputs.
 * @details This function selects peripheral inputs that will be routed from predefined 
 *          TRGMUX outputs.
 * @param   pers  Mask of @ref siul_periph_inputs_from_trgmux_outputs.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_Init, @ref TRGMUX_SetPath
 ******************************************************************************/
#define SIUL_SetTrgmuxPath(pers) VSIUL_SetTrgmuxPath(0,pers)
#define VSIUL_SetTrgmuxPath(slot,pers)                              \
do{                                                                 \
  if((pers) & SIUL_eMIOS0CH10)  prvVSIUL[slot]->IMCR[58] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH11)  prvVSIUL[slot]->IMCR[59] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH12)  prvVSIUL[slot]->IMCR[60] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH13)  prvVSIUL[slot]->IMCR[61] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH14)  prvVSIUL[slot]->IMCR[62] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH15)  prvVSIUL[slot]->IMCR[63] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH1 )  prvVSIUL[slot]->IMCR[49] = 0b0101u; \
  if((pers) & SIUL_eMIOS0CH2 )  prvVSIUL[slot]->IMCR[50] = 0b0101u; \
  if((pers) & SIUL_eMIOS0CH3 )  prvVSIUL[slot]->IMCR[51] = 0b0110u; \
  if((pers) & SIUL_eMIOS0CH4 )  prvVSIUL[slot]->IMCR[52] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH5 )  prvVSIUL[slot]->IMCR[53] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH6 )  prvVSIUL[slot]->IMCR[54] = 0b0011u; \
  if((pers) & SIUL_eMIOS0CH7 )  prvVSIUL[slot]->IMCR[55] = 0b0100u; \
  if((pers) & SIUL_eMIOS0CH9 )  prvVSIUL[slot]->IMCR[57] = 0b0011u; \
  if((pers) & SIUL_eMIOS1CH10)  prvVSIUL[slot]->IMCR[90] = 0b0101u; \
  if((pers) & SIUL_eMIOS1CH11)  prvVSIUL[slot]->IMCR[91] = 0b0100u; \
  if((pers) & SIUL_eMIOS1CH12)  prvVSIUL[slot]->IMCR[92] = 0b0110u; \
  if((pers) & SIUL_eMIOS1CH13)  prvVSIUL[slot]->IMCR[93] = 0b0100u; \
  if((pers) & SIUL_eMIOS1CH14)  prvVSIUL[slot]->IMCR[94] = 0b0100u; \
  if((pers) & SIUL_eMIOS1CH15)  prvVSIUL[slot]->IMCR[95] = 0b0101u; \
  if((pers) & SIUL_eMIOS1CH1 )  prvVSIUL[slot]->IMCR[81] = 0b0110u; \
  if((pers) & SIUL_eMIOS1CH2 )  prvVSIUL[slot]->IMCR[82] = 0b0110u; \
  if((pers) & SIUL_eMIOS1CH3 )  prvVSIUL[slot]->IMCR[83] = 0b0110u; \
  if((pers) & SIUL_eMIOS1CH4 )  prvVSIUL[slot]->IMCR[84] = 0b0110u; \
  if((pers) & SIUL_eMIOS1CH5 )  prvVSIUL[slot]->IMCR[85] = 0b0111u; \
  if((pers) & SIUL_eMIOS1CH6 )  prvVSIUL[slot]->IMCR[86] = 0b0110u; \
  if((pers) & SIUL_eMIOS1CH7 )  prvVSIUL[slot]->IMCR[87] = 0b0110u; \
  if((pers) & SIUL_eMIOS1CH9 )  prvVSIUL[slot]->IMCR[89] = 0b0100u; \
}while(0)

/***************************************************************************//*!
 * @brief   Enable reset input filter.
 * @details This macro enables input filter for reset pin (PTA5).
 * @note    Implemented as a macro.
 ******************************************************************************/
#define SIUL_EnableResetInputFilter() VSIUL_EnableResetInputFilter(0)
#define VSIUL_EnableResetInputFilter(slot) \
  do{ prvVSIUL[slot]->MSCR[5]|=SIUL2_MSCR_IFE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disable reset input filter.
 * @details This macro disables input filter for reset pin (PTA5).
 * @note    Implemented as a macro.
 ******************************************************************************/
#define SIUL_DisableResetInputFilter() VSIUL_DisableResetInputFilter(0)
#define VSIUL_DisableResetInputFilter(slot) \
  do{ prvVSIUL[slot]->MSCR[5]&=~SIUL2_MSCR_IFE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Returns state of pin.
 * @details This macro returns state of pin(s).
 * @param   port    One of @ref siul_ports.
 * @param   pin     One of @ref siul_pins.
 * @return  @ref uint8_t value.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_SetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_TglPin, 
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_GetPin(port,pin) port##_##pin##_GPDI(0)
#define VSIUL_GetPin(slot,port,pin) port##_##pin##_GPDI(slot)

/***************************************************************************//*!
 * @brief   Set state of pin.
 * @details This macro sets state of pin.
 * @param   port    One of @ref siul_ports.
 * @param   pin     One of @ref siul_pins.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_GetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_TglPin, 
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_SetPin(port,pin) do{ port##_##pin##_GPDO(0) = 1u; }while(0)
#define VSIUL_SetPin(slot,port,pin) do{ port##_##pin##_GPDO(slot) = 1u; }while(0)

/***************************************************************************//*!
 * @brief   Enable output buffer of pin.
 * @details This macro enables output buffer of selected pin.
 * @param   port    One of @ref siul_ports.
 * @param   pin     One of @ref siul_pins.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_GetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_TglPin,
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_EnableOutBuff(port,pin) \
  do{ port##_##pin##_MSCR(0) |= SIUL2_MSCR_OBE_MASK; }while(0)
#define VSIUL_EnableOutBuff(slot,port,pin) \
  do{ port##_##pin##_MSCR(slot) |= SIUL2_MSCR_OBE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Disable output buffer of pin.
 * @details This macro disables output buffer of selected pin.
 * @param   port    One of @ref siul_ports.
 * @param   pin     One of @ref siul_pins.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_GetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_TglPin,
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_DisableOutBuff(port,pin) \
  do{ port##_##pin##_MSCR(0) &= ~SIUL2_MSCR_OBE_MASK; }while(0)
#define VSIUL_DisableOutBuff(slot,port,pin) \
  do{ port##_##pin##_MSCR(slot) &= ~SIUL2_MSCR_OBE_MASK; }while(0)

/***************************************************************************//*!
 * @brief   Set state of pin by value.
 * @details This macro sets state of pin specified by input parameter value.
 * @param   port    One of @ref siul_ports.
 * @param   pin     One of @ref siul_pins.
 * @param   value   [0,1].
 * @note    Implemented as a macro.
 * @see     @ref SIUL_SetPin, @ref SIUL_GetPin, @ref SIUL_ClrPin, @ref SIUL_TglPin, 
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_SetPinVal(port,pin,value) \
  do{ port##_##pin##_GPDO(0) = value; }while(0)
#define VSIUL_SetPinVal(slot,port,pin,value) \
  do{ port##_##pin##_GPDO(slot) = value; }while(0)

/***************************************************************************//*!
 * @brief   Clear state of pin.
 * @details This macro clears state of pin.
 * @param   port    One of @ref siul_ports.
 * @param   pin     One of @ref siul_pins.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_SetPin, @ref SIUL_SetPinVal,@ref SIUL_GetPin, @ref SIUL_TglPin, 
 *          @ref SIUL_SetGrpVal,@ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_ClrPin(port,pin) do{ port##_##pin##_GPDO(0) = 0u; }while(0)
#define VSIUL_ClrPin(slot,port,pin) do{ port##_##pin##_GPDO(slot) = 0u; }while(0)

/***************************************************************************//*!
 * @brief   Toggle state of pin.
 * @details This macro toggles state of pin.
 * @param   port    One of @ref siul_ports.
 * @param   pin     One of @ref siul_pins.
 * @see     @ref SIUL_SetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_GetPin, 
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_TglPin(port,pin) \
  do{ port##_##pin##_GPDO(0) = ~port##_##pin##_GPDO(0); }while(0)
#define VSIUL_TglPin(slot,port,pin) \
  do{ port##_##pin##_GPDO(slot) = ~port##_##pin##_GPDO(slot); }while(0)

/***************************************************************************//*!
 * @brief   Set state of pin group by value.
 * @details This macro sets state of pin group by value.
 * @param   group    One of @ref siul_groups.
 * @param   value    @ref uint32_t.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_SetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_TglPin, 
 *          @ref SIUL_GetPin, @ref SIUL_GetGrpVal, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_SetGrpVal(group,value) do{ group##_PGDO(0) = value; }while(0)
#define VSIUL_SetGrpVal(slot,group,value) do{ group##_PGDO(slot) = value; }while(0)

/***************************************************************************//*!
 * @brief   Returns state of pin group.
 * @details This macro returns state of pin group.
 * @param   group    One of @ref siul_groups
 * @return  @ref uint32_t value.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_SetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_TglPin, 
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetPin, @ref SIUL_SetGrpMaskedVal
 ******************************************************************************/
#define SIUL_GetGrpVal(group) group##_PGDI(0)
#define VSIUL_GetGrpVal(slot,group) group##_PGDI(slot)

/***************************************************************************//*!
 * @brief   Set state of pin group by masked value.
 * @details This macro sets state of pin group by masked value.
 * @param   group    One of @ref siul_groups
 * @param   mask     @ref uint16_t.
 * @param   value    @ref uint16_t.
 * @note    Implemented as a macro.
 * @see     @ref SIUL_SetPin, @ref SIUL_SetPinVal, @ref SIUL_ClrPin, @ref SIUL_TglPin, 
 *          @ref SIUL_SetGrpVal, @ref SIUL_GetGrpVal, @ref SIUL_GetPin
 ******************************************************************************/
#define SIUL_SetGrpMaskedVal(group,mask,value) \
  do{ group##_MPGDO(0) =((uint32_t)(mask<<16) | value); }while(0)
#define VSIUL_SetGrpMaskedVal(slot,group,mask,value) \
  do{ group##_MPGDO(slot) =((uint32_t)(mask<<16) | value); }while(0)

/***************************************************************************//*!
 * @brief   Sets glitch filter prescaler.
 * @details This macro sets glitch filter prescaler.
 * @param   presc    Clock prescaler [0..15].
 * @note    Implemented as a macro.
 * @see     @ref SIUL_Init, @ref SIUL_InstallCallback, @ref SIUL_EnableIrq, 
 *          @ref SIUL_EnableDma
 ******************************************************************************/
#define SIUL_SetGlitchFilterPresc(presc) \
  do{ prvVSIUL[0]->IFCPR = presc; }while(0)
#define VSIUL_SetGlitchFilterPresc(slot,presc) \
  do{ prvVSIUL[slot]->IFCPR = presc; }while(0)

/***************************************************************************//*!
 * @brief   Enables interrupt requests of the SIUL module.
 * @details This function enables interrupt requests of the SIUL module.
 * @param   posedge Mask of @ref siul_irq_req enabled on posedge.
 * @param   negedge Mask of @ref siul_irq_req enabled on negedge.
 * @param   maxcnt  Glitch filter counts [-1 (filter disabled),0..15].
 * @note    Implemented as a macro.
 * @see     @ref SIUL_Init, @ref SIUL_InstallCallback, @ref SIUL_EnableDma, 
 *          @ref SIUL_SetGlitchFilterPresc
 ******************************************************************************/
#define SIUL_EnableIrq(posedge,negedge,maxcnt) \
  VSIUL_EnableIrq(0,posedge,negedge,maxcnt)
#define VSIUL_EnableIrq(slot,posedge,negedge,maxcnt)        \
do{                                                         \
  register uint32_t tmp = (posedge)|(negedge);              \
  prvVSIUL[slot]->IREER0 |= (posedge);                      \
  prvVSIUL[slot]->IFEER0 |= (negedge);                      \
  prvVSIUL[slot]->DIRSR0 &= ~tmp;                           \
  prvVSIUL[slot]->DISR0 = 0xFFFFFFFFU;                      \
  if (maxcnt >= 0)                                          \
  {                                                         \
    prvVSIUL[slot]->IFER0 |= tmp;                           \
    if(tmp & IRQ_REQ0 ) prvVSIUL[slot]->IFMCR[0]  = maxcnt; \
    if(tmp & IRQ_REQ1 ) prvVSIUL[slot]->IFMCR[1]  = maxcnt; \
    if(tmp & IRQ_REQ2 ) prvVSIUL[slot]->IFMCR[2]  = maxcnt; \
    if(tmp & IRQ_REQ3 ) prvVSIUL[slot]->IFMCR[3]  = maxcnt; \
    if(tmp & IRQ_REQ4 ) prvVSIUL[slot]->IFMCR[4]  = maxcnt; \
    if(tmp & IRQ_REQ5 ) prvVSIUL[slot]->IFMCR[5]  = maxcnt; \
    if(tmp & IRQ_REQ6 ) prvVSIUL[slot]->IFMCR[6]  = maxcnt; \
    if(tmp & IRQ_REQ7 ) prvVSIUL[slot]->IFMCR[7]  = maxcnt; \
    if(tmp & IRQ_REQ8 ) prvVSIUL[slot]->IFMCR[8]  = maxcnt; \
    if(tmp & IRQ_REQ9 ) prvVSIUL[slot]->IFMCR[9]  = maxcnt; \
    if(tmp & IRQ_REQ10) prvVSIUL[slot]->IFMCR[10] = maxcnt; \
    if(tmp & IRQ_REQ11) prvVSIUL[slot]->IFMCR[11] = maxcnt; \
    if(tmp & IRQ_REQ12) prvVSIUL[slot]->IFMCR[12] = maxcnt; \
    if(tmp & IRQ_REQ13) prvVSIUL[slot]->IFMCR[13] = maxcnt; \
    if(tmp & IRQ_REQ14) prvVSIUL[slot]->IFMCR[14] = maxcnt; \
    if(tmp & IRQ_REQ15) prvVSIUL[slot]->IFMCR[15] = maxcnt; \
    if(tmp & IRQ_REQ16) prvVSIUL[slot]->IFMCR[16] = maxcnt; \
    if(tmp & IRQ_REQ17) prvVSIUL[slot]->IFMCR[17] = maxcnt; \
    if(tmp & IRQ_REQ18) prvVSIUL[slot]->IFMCR[18] = maxcnt; \
    if(tmp & IRQ_REQ19) prvVSIUL[slot]->IFMCR[19] = maxcnt; \
    if(tmp & IRQ_REQ20) prvVSIUL[slot]->IFMCR[20] = maxcnt; \
    if(tmp & IRQ_REQ21) prvVSIUL[slot]->IFMCR[21] = maxcnt; \
    if(tmp & IRQ_REQ22) prvVSIUL[slot]->IFMCR[22] = maxcnt; \
    if(tmp & IRQ_REQ23) prvVSIUL[slot]->IFMCR[23] = maxcnt; \
    if(tmp & IRQ_REQ24) prvVSIUL[slot]->IFMCR[24] = maxcnt; \
    if(tmp & IRQ_REQ25) prvVSIUL[slot]->IFMCR[25] = maxcnt; \
    if(tmp & IRQ_REQ26) prvVSIUL[slot]->IFMCR[26] = maxcnt; \
    if(tmp & IRQ_REQ27) prvVSIUL[slot]->IFMCR[27] = maxcnt; \
    if(tmp & IRQ_REQ28) prvVSIUL[slot]->IFMCR[28] = maxcnt; \
    if(tmp & IRQ_REQ29) prvVSIUL[slot]->IFMCR[29] = maxcnt; \
    if(tmp & IRQ_REQ30) prvVSIUL[slot]->IFMCR[30] = maxcnt; \
    if(tmp & IRQ_REQ31) prvVSIUL[slot]->IFMCR[31] = maxcnt; \
  }                                                         \
  else { prvVSIUL[slot]->IFER0 &= ~tmp; }                   \
  prvVSIUL[slot]->DIRER0 |= tmp;                            \
}while(0)

/***************************************************************************//*!
 * @brief   Enables DMA requests of the SIUL module.
 * @details This function enables DMA requests of the SIUL module.
 * @param   posedge Mask of @ref siul_dma_req enabled on posedge.
 * @param   negedge Mask of @ref siul_dma_req enabled on negedge.
 * @param   maxcnt  Glitch filter counts [-1 (filter disabled),0..15].
 * @note    Implemented as a macro.
 * @see     @ref SIUL_Init, @ref SIUL_InstallCallback, @ref SIUL_EnableIrq, 
 *          @ref SIUL_SetGlitchFilterPresc
 ******************************************************************************/
#define SIUL_EnableDma(posedge,negedge,maxcnt) \
  VSIUL_EnableDma(0,posedge,negedge,maxcnt)
#define VSIUL_EnableDma(slot,posedge,negedge,maxcnt)        \
do{                                                         \
  register uint32_t tmp = (posedge)|(negedge);              \
                                                            \
  prvVSIUL[slot]->IREER0 |= (posedge);                      \
  prvVSIUL[slot]->IFEER0 |= (negedge);                      \
  prvVSIUL[slot]->DIRSR0 |= tmp;                            \
  prvVSIUL[slot]->DISR0 = 0xFFFFFFFFU;                      \
  if (maxcnt >= 0)                                          \
  {                                                         \
    prvVSIUL[slot]->IFER0 |= tmp;                           \
    if(tmp & IRQ_REQ0 ) prvVSIUL[slot]->IFMCR[0]  = maxcnt; \
    if(tmp & IRQ_REQ1 ) prvVSIUL[slot]->IFMCR[1]  = maxcnt; \
    if(tmp & IRQ_REQ2 ) prvVSIUL[slot]->IFMCR[2]  = maxcnt; \
    if(tmp & IRQ_REQ3 ) prvVSIUL[slot]->IFMCR[3]  = maxcnt; \
    if(tmp & IRQ_REQ4 ) prvVSIUL[slot]->IFMCR[4]  = maxcnt; \
    if(tmp & IRQ_REQ5 ) prvVSIUL[slot]->IFMCR[5]  = maxcnt; \
    if(tmp & IRQ_REQ6 ) prvVSIUL[slot]->IFMCR[6]  = maxcnt; \
    if(tmp & IRQ_REQ7 ) prvVSIUL[slot]->IFMCR[7]  = maxcnt; \
    if(tmp & IRQ_REQ8 ) prvVSIUL[slot]->IFMCR[8]  = maxcnt; \
    if(tmp & IRQ_REQ9 ) prvVSIUL[slot]->IFMCR[9]  = maxcnt; \
    if(tmp & IRQ_REQ10) prvVSIUL[slot]->IFMCR[10] = maxcnt; \
    if(tmp & IRQ_REQ11) prvVSIUL[slot]->IFMCR[11] = maxcnt; \
    if(tmp & IRQ_REQ12) prvVSIUL[slot]->IFMCR[12] = maxcnt; \
    if(tmp & IRQ_REQ13) prvVSIUL[slot]->IFMCR[13] = maxcnt; \
    if(tmp & IRQ_REQ14) prvVSIUL[slot]->IFMCR[14] = maxcnt; \
    if(tmp & IRQ_REQ15) prvVSIUL[slot]->IFMCR[15] = maxcnt; \
    if(tmp & IRQ_REQ16) prvVSIUL[slot]->IFMCR[16] = maxcnt; \
    if(tmp & IRQ_REQ17) prvVSIUL[slot]->IFMCR[17] = maxcnt; \
    if(tmp & IRQ_REQ18) prvVSIUL[slot]->IFMCR[18] = maxcnt; \
    if(tmp & IRQ_REQ19) prvVSIUL[slot]->IFMCR[19] = maxcnt; \
    if(tmp & IRQ_REQ20) prvVSIUL[slot]->IFMCR[20] = maxcnt; \
    if(tmp & IRQ_REQ21) prvVSIUL[slot]->IFMCR[21] = maxcnt; \
    if(tmp & IRQ_REQ22) prvVSIUL[slot]->IFMCR[22] = maxcnt; \
    if(tmp & IRQ_REQ23) prvVSIUL[slot]->IFMCR[23] = maxcnt; \
    if(tmp & IRQ_REQ24) prvVSIUL[slot]->IFMCR[24] = maxcnt; \
    if(tmp & IRQ_REQ25) prvVSIUL[slot]->IFMCR[25] = maxcnt; \
    if(tmp & IRQ_REQ26) prvVSIUL[slot]->IFMCR[26] = maxcnt; \
    if(tmp & IRQ_REQ27) prvVSIUL[slot]->IFMCR[27] = maxcnt; \
    if(tmp & IRQ_REQ28) prvVSIUL[slot]->IFMCR[28] = maxcnt; \
    if(tmp & IRQ_REQ29) prvVSIUL[slot]->IFMCR[29] = maxcnt; \
    if(tmp & IRQ_REQ30) prvVSIUL[slot]->IFMCR[30] = maxcnt; \
    if(tmp & IRQ_REQ31) prvVSIUL[slot]->IFMCR[31] = maxcnt; \
  }                                                         \
  else { prvVSIUL[slot]->IFER0 &= ~tmp; }                   \
  prvVSIUL[slot]->DIRER0 |= tmp;                            \
}while(0)

/******************************************************************************
 * public function prototypes                                                 *
 ******************************************************************************/
/***************************************************************************//*!
 * @brief   Installs callback function for interrupt vector depended on SIUL module.
 * @details This function install callback function for interrupt vector.
 * @param   vector    One of @ref siul_irq_groups.
 * @param   ip        @ref irq_prilvl "Interrupt Priority Levels".
 * @param   callback  Pointer to the @ref tSIUL_CALLBACK.
 * @note    Implemented as a function call.
 * @see     @ref SIUL_Init, @ref SIUL_EnableIrq, @ref SIUL_EnableDma, 
 *          @ref SIUL_SetGlitchFilterPresc
 ******************************************************************************/
#define SIUL_InstallCallback(vector,ip,callback) \
  VSIUL_InstallCallback (0,vector,ip,callback)
#define VSIUL_InstallCallback(slot,vector,ip,callback) \
  VSIUL_prvInstallCallback(slot,vector,ip,callback)
/*! @} End of siul_macro                                                      */

/******************************************************************************
 * public function prototypes                                                 *
 ******************************************************************************/
void VSIUL_prvInstallCallback (uint16_t slot, uint8_t vector, uint8_t ip, tSIUL_CALLBACK pCallback);

/******************************************************************************
 * interrupt handler prototypes                                               *
 ******************************************************************************/
void SIUL_0_Handler (void);
void SIUL_1_Handler (void);
void SIUL_2_Handler (void);
void SIUL_3_Handler (void);

#endif /* __SIUL_H */
