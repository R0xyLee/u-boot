/* SPDX-License-Identifier: GPL-2.0+ */

#ifndef __OK8MP_H
#define __OK8MP_H

#include <linux/sizes.h>
#include <asm/arch/imx-regs.h>

#define CFG_SYS_UBOOT_BASE	(QSPI0_AMBA_BASE + CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR * 512)
#define CFG_FEC_MXC_PHYADDR	1
#define CFG_SYS_INIT_RAM_ADDR	0x40000000
#define CFG_SYS_INIT_RAM_SIZE	SZ_512K
#define CFG_SYS_SDRAM_BASE	0x40000000
#define PHYS_SDRAM		0x40000000
#define PHYS_SDRAM_SIZE		0xc0000000
#define PHYS_SDRAM_2		0x100000000
#define PHYS_SDRAM_2_SIZE		0x40000000

#endif
