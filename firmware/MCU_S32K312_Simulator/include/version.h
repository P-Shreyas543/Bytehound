/******************************************************************************
 * (c) Copyright 2018-2020, NXP Semiconductor Inc.
 * ALL RIGHTS RESERVED.
 ***************************************************************************//*!
 * @file      version.h
 * @brief     Defines the bare-metal drivers version constants
 ******************************************************************************/
#ifndef __VERSION_H
#define __VERSION_H

/******************************************************************************
 * release       symbol                                         value
 ******************************************************************************
 * 1.1-Alpha     S32K3_BMDRV_VERSION_1_1_ALPHA                  0x0101
 * 1.1-Beta      S32K3_BMDRV_VERSION_1_1_BETA                   0x0101
 * 1.1           S32K3_BMDRV_VERSION_1_1                        0x0101
 ******************************************************************************/
#define VERSION_MAKE(major,minor)   ((major)<<8 | (minor))

#define S32K3_BMDRV_VERSION         VERSION_MAKE(1,1)
#define S32K3_BMDRV_VERSION_1_1_BETA

#endif /* __VERSION_H */
