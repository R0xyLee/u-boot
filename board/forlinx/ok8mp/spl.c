// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Based on the i.MX8MP EVK SPL, Copyright 2018-2019, 2021 NXP.
 * PMIC settings follow the Forlinx 4 GiB reference image.
 */

#include <debug_uart.h>
#include <hang.h>
#include <init.h>
#include <spl.h>
#include <asm/arch/clock.h>
#include <asm/arch/ddr.h>
#include <asm/arch/sys_proto.h>
#include <asm/mach-imx/boot_mode.h>
#include <asm/global_data.h>
#include <linux/kernel.h>
#include <linux/libfdt.h>
#include <power/pca9450.h>
#include <power/pmic.h>

DECLARE_GLOBAL_DATA_PTR;

int spl_board_boot_device(enum boot_device boot_dev_spl)
{
	return BOOT_DEVICE_BOOTROM;
}

ulong spl_romapi_get_uboot_base(u32 image_offset, u32 rom_bt_dev)
{
	/* Keep ROMAPI independent of the disabled native MMC loader. */
	return (ulong)image_offset + CONFIG_OK8MP_FIT_OFFSET;
}

int power_init_board(void)
{
	static const struct {
		u8 reg;
		u8 value;
	} setup[] = {
		{ PCA9450_BUCK123_DVS, 0x29 },
		/* VDD_SOC: 0.95 V running, 0.85 V standby. */
		{ PCA9450_BUCK1OUT_DVS0, 0x1c },
		{ PCA9450_BUCK1OUT_DVS1, 0x14 },
		{ PCA9450_BUCK1CTRL, 0x59 },
		/* VDD_ARM: 0.95 V, before enabling overdrive clocks. */
		{ PCA9450_BUCK2OUT_DVS0, 0x1c },
		/* Match the module's reference reset configuration. */
		{ PCA9450_RESET_CTRL, 0xa1 },
	};
	struct udevice *dev;
	int i, ret;

	ret = pmic_get("pmic@25", &dev);
	if (ret)
		return ret;

	for (i = 0; i < ARRAY_SIZE(setup); i++) {
		ret = pmic_reg_write(dev, setup[i].reg, setup[i].value);
		if (ret)
			return ret;
	}

	return 0;
}

void spl_board_init(void)
{
	const char *required;
	int node, len;

	/* An unprovisioned SPL must not silently accept unsigned FITs. */
	node = fdt_path_offset(gd->fdt_blob, "/signature/key-boot");
	required = fdt_getprop(gd->fdt_blob, node, "required", &len);
	if (!IS_ENABLED(CONFIG_SPL_FIT_SIGNATURE) || !required ||
	    len != sizeof("conf") || memcmp(required, "conf", sizeof("conf")))
		panic("SPL: required FIT verification key is missing\n");

	arch_misc_init();

	/* Set the GIC to 500 MHz only after the PMIC supplies 0.95 V. */
	clock_enable(CCGR_GIC, 0);
	clock_set_target_val(GIC_CLK_ROOT, CLK_ROOT_ON | CLK_ROOT_SOURCE_SEL(5));
	clock_enable(CCGR_GIC, 1);
}

int board_fit_config_name_match(const char *name)
{
	/* The image contains a single board configuration. */
	return 0;
}

void board_init_f(ulong dummy)
{
	int ret;

	printascii("OK8MP SPL: early init\n");
	arch_cpu_init();

	ret = spl_early_init();
	if (ret) {
		printascii("SPL early init failed, error=0x");
		printhex8(ret);
		printascii(" heap_used=0x");
		printhex8(gd->malloc_ptr);
		printascii("\n");
		hang();
	}

	preloader_console_init();
	printf("SPL: early heap %u/%u bytes\n", gd->malloc_ptr,
	       CONFIG_SPL_SYS_MALLOC_F_LEN);
	enable_tzc380();

	ret = power_init_board();
	if (ret) {
		printf("PCA9450 initialization failed: %d\n", ret);
		hang();
	}

	puts("DDR: OK8MP 4 GiB static timing (4000 MT/s)\n");
	ret = ddr_init(&dram_timing);
	if (ret) {
		printf("DDR initialization failed: %d\n", ret);
		hang();
	}

	puts("DDR: training complete\n");
}
