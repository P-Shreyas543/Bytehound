/******************************************************************************
 * (c) Copyright 2018-2020, NXP Semiconductor Inc.
 * ALL RIGHTS RESERVED.
 ***************************************************************************//*!
 * @file      defconfig.h
 * @brief     Header file.
 ******************************************************************************/
#ifndef __DEFCONFIG_H
#define __DEFCONFIG_H

/******************************************************************************
 * Static configurations functions and macros
 *
 *//*! @addtogroup project_config
 * @{
 ******************************************************************************/
/***************************************************************************//*!
 * @brief Configures placement of driver's interrupt handlers in memory region.
 * @details Configures placement of driver's interrupt handlers in memory region
 * based on the value of @ref configHANDLER_IN_TCM define in <c>appconfig.h</c>
 * as show below:
 * |configHANDLER_IN_TCM  |0            |1              |
 * |:--------------------:|:-----------:|:-------------:|
 * |Memory region         |PROM         |ITCM           |
 * |Section               |.text        |.itcm.$func    |
 * |Memory description    |Program Flash|Instruction TCM|
 * |Section initialization|-            |Startup        |
 * @note  Missing definition in <c>appconfig.h</c> will result in interrupt handlers
 * placement in Program Flash (default).
 ******************************************************************************/
#ifndef configHANDLER_IN_TCM
#define configHANDLER_IN_TCM 0
#endif

#if configHANDLER_IN_TCM == 1
#define __HANDLERFUNC __tcmfunc
#else
#define __HANDLERFUNC
#endif

/***************************************************************************//*!
 * @brief Configures placement of driver's runtime functions in memory region.
 * @details Configures placement of driver's runtime functions in memory region
 * based on the value of @ref configRUNTIME_IN_TCM define in <c>appconfig.h</c>
 * as show below:
 * |configRUNTIME_IN_TCM  |0            |1              |
 * |:--------------------:|:-----------:|:-------------:|
 * |Memory region         |PROM         |ITCM           |
 * |Section               |.text        |.itcm.$func    |
 * |Memory description    |Program Flash|Instruction TCM|
 * |Section initialization|-            |Startup        |
 * @note  Missing definition in <c>appconfig.h</c> will result in runtime functions
 * placement in Program Flash (default).
 ******************************************************************************/
#ifndef configRUNTIME_IN_TCM
#define configRUNTIME_IN_TCM 0
#endif

#if configHANDLER_IN_TCM == 1
#define __RUNTIMEFUNC __tcmfunc
#else
#define __RUNTIMEFUNC
#endif

/***************************************************************************//*!
 * @brief Predefined clock configurations applied in <c>userPreMain</c> function.
 * @details Configures clock based on the value of @ref configCLOCK_MODE define in
 * <c>appconfig.h</c> file as show below:
 * |configCLOCK_MODE     |5                     |4                     |3                                 |2                           |1                               |
 * |:-------------------:|:--------------------:|:--------------------:|:--------------------:|:-------------------:|:------------------------------:|
 * |Description          |Clocked by PLL 240 MHz|Clocked by PLL 160 MHz|Clocked by PLL 120 MHz            |Clocked by PLL 80 MHz       |Clocked by FIRC 48 MHz (default)|
 * |Configuration        |Clock sources and frequencies in MHz                                                                                                      |||||
 * |PLL source           |FXOSC                 |FXOSC                 |FXOSC                             |FXOSC                       |-                               |
 * |Clock source         |PLL                   |PLL                   |PLL                               |PLL                         |FIRC                            |
 * |PLL_PHI0_CLK         |240                   |160                   |120                               |80                          |-                               |
 * |PLL_PHI1_CLK         |240                   |240                   |48                    |48                   |-                               |
 * |CORE_CLK             |240                   |160                   |120                               |80                          |48                              |
 * |AIPS_PLAT_CLK        |120                   |80                    |60                                |80                          |48                              |
 * |AIPS_SLOW_CLK        |60                    |40                    |30                                |40                          |24                              |
 * |HSE_CLK              |120                   |80                    |120                               |80                          |48                              |
 * |DCM_CLK              |60                    |40                    |30                                |40                          |48                              |
 * |LBIST_CLK            |60                    |40                    |30                                |40                          |48                              |
 * |QSPI_MEM_CLK         |120                   |120                   |120                               |80                          |48                              |
 * |Gasket type and mode |Default configurations (bare-metal drivers don't configure gaskets in bypass mode)                                                        |||||
 * |EDMA                 |1:1                   |1:1                   |bypass                            |bypass                      |bypass                          |
 * |HSE                  |1:2                   |1:2                   |1:1                               |bypass                      |bypass                          |
 * |AIPS 1/2             |2:1                   |2:1                   |2:1                               |bypass                      |bypass                          |
 * |QSPI                 |2:1                   |2:1                   |2:1                               |bypass                      |bypass                          |
 * |ENET 32:64           |1:2                   |1:2                   |1:2                               |1:1                         |1:1                             |
 * |Wait states          |Default configurations                                                                                                                    |||||
 * |Flash read (RWSC)    |7                     |4                     |3                                 |2                           |1                               |
 * |SRAM read  (FT_DIS)  |1                     |1                     |1                     |0                    |0                               |
 * @note  Missing definition in <c>appconfig.h</c> will configure clock in default
 * FIRC 48 MHz clock mode. The value of 5 will force max. clock frequency that can
 * be used for given target.
 ******************************************************************************/
#ifndef configCLOCK_MODE
#define configCLOCK_MODE 1
#endif

#if configCLOCK_MODE == 0
#undef configCLOCK_MODE
#define configCLOCK_MODE 1
#endif

#if configCLOCK_MODE == 5
#undef configCLOCK_MODE
#define configCLOCK_MODE 3
#endif

#if configCLOCK_MODE == 4
#undef configCLOCK_MODE
#define configCLOCK_MODE 3
#endif

#if configCLOCK_MODE > 5
#error "Unknown clock mode (configCLOCK_MODE)"
#endif

/***************************************************************************//*!
 * @brief Predefined FXOSC frequency configurations.
 * @details Configures frequency of the crystal based on the value of @ref
 * configXTAL_FREQ define in <c>appconfig.h</c> file as show below:
 * |configXTAL_FREQ|0                            |1    |2     |3     |4     |5     |6     |
 * |:-------------:|:---------------------------:|:---:|:----:|:----:|:----:|:----:|:----:|
 * |Description    |No external crystal (default)|8 MHz|16 MHz|20 MHz|24 MHz|32 MHz|40 MHz|
 * @note  Missing definition in <c>appconfig.h</c> will result in no external
 * crystal being considered to be connected (default). The FXOSC frequency
 * configurations defined by configXTAL_FREQ is used only if
 * @ref configCLOCK_MODE >= 2.
 ******************************************************************************/
#ifndef configXTAL_FREQ
#define configXTAL_FREQ 0
#endif

#if (configXTAL_FREQ == 0) && (configCLOCK_MODE > 1)
#error "Selected clock mode (configCLOCK_MODE) cannot be used without external crystal"
#endif

#if configXTAL_FREQ > 6
#error "Unknown crystal frequency (configXTAL_FREQ)"
#endif
/*! @} End of project_config                                                  */

#endif /* __DEFCONFIG_H */
