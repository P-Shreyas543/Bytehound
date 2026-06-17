/*
 * Copyright 2018-2020, 2024 NXP
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * @file      mcme.c
 * @brief     Mode Entry Module (MCME) driver source code.
 */
#include "common.h"
#include "mcme.h"

/******************************************************************************
* Private definitions to simplify driver
*******************************************************************************/
const uint32_t coreid_pidx[] = {0U,0U,0U}; /* partition index of the core     */
const uint32_t coreid_cidx[] = {0U,0U,1U}; /* core index inside the partition */

/******************************************************************************
 * End of module                                                              *
 ******************************************************************************/
