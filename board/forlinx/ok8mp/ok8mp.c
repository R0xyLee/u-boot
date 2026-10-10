// SPDX-License-Identifier: GPL-2.0+

#include <init.h>
#include <env.h>
#include <net.h>
#include <stdio.h>
#include <asm/arch/clock.h>
#include <asm/arch/imx-regs.h>
#include <asm/arch/imx8mp_pins.h>
#include <asm/arch/sys_proto.h>
#include <asm/io.h>
#include <asm/mach-imx/iomux-v3.h>
#include <u-boot/sha256.h>

void board_debug_uart_init(void)
{
	static const iomux_v3_cfg_t uart_pads[] = {
		MX8MP_PAD_UART2_RXD__UART2_DCE_RX | MUX_PAD_CTRL(0x49),
		MX8MP_PAD_UART2_TXD__UART2_DCE_TX | MUX_PAD_CTRL(0x49),
	};

	/* The driver model and its early heap are not available yet. */
	imx_iomux_v3_setup_multiple_pads(uart_pads, ARRAY_SIZE(uart_pads));
	init_uart_clk(1);
}

int checkboard(void)
{
	puts("Board: Forlinx OK8MP-C V3.1, 4 GiB LPDDR4\n");

	return 0;
}

static int ok8mp_setup_mac(int index)
{
	struct ocotp_regs *ocotp = (struct ocotp_regs *)OCOTP_BASE_ADDR;
	struct fuse_bank0_regs *fuse = (struct fuse_bank0_regs *)ocotp->bank[0].fuse_regs;
	u8 mac[ARP_HLEN], digest[SHA256_SUM_LEN];
	__be32 uid[2];
	u32 low, high;

	if (eth_env_get_enetaddr_by_index("eth", index, mac))
		return 0;

	imx_get_mac_from_fuse(index, mac);
	if (is_valid_ethaddr(mac))
		return eth_env_set_enetaddr_by_index("eth", index, mac);

	low = readl(&fuse->uid_low);
	high = readl(&fuse->uid_high);
	if ((!low && !high) || (low == ~0U && high == ~0U))
		return -ENODATA;

	/* Stable local addresses for modules without programmed MAC fuses. */
	uid[0] = cpu_to_be32(high);
	uid[1] = cpu_to_be32(low);
	sha256_csum_wd((u8 *)uid, sizeof(uid), digest, CHUNKSZ_SHA256);
	memcpy(mac, digest, sizeof(mac));
	mac[0] = (mac[0] & 0xfc) | 0x02;
	mac[5] ^= index;

	return eth_env_set_enetaddr_by_index("eth", index, mac);
}

int board_late_init(void)
{
	int index;
	int ret;

	for (index = 0; index < 2; index++) {
		ret = ok8mp_setup_mac(index);
		if (ret)
			printf("Failed to set eth%d MAC address: %d\n", index, ret);
	}

	if (!is_usb_boot())
		return 0;

	/* Let UUU reconnect to Fastboot after the ROM downloads the image. */
	ret = env_set("bootcmd", "fastboot usb 0");
	if (ret)
		return ret;

	return env_set("bootdelay", "0");
}
