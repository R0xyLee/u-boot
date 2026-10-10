#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Extract the DDR PHY firmware windows from the identified Forlinx image."""

import argparse
import hashlib
from pathlib import Path


SOURCE_SHA256 = "7fc2a09046762d92b8aab67748a640151d609c439e08d5b3f74c9bb62554e4d5"
FIRMWARE = (
	("ok8mp-lpddr4-1d-imem.bin", 0xEF50, 0x8000),
	("ok8mp-lpddr4-1d-dmem.bin", 0x16F50, 0x4000),
	("ok8mp-lpddr4-2d-imem.bin", 0x1AF50, 0x8000),
	("ok8mp-lpddr4-2d-dmem.bin", 0x22F50, 0x4000),
)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("image", type=Path, help="unmodified vendor imx-boot_4G.bin")
	parser.add_argument("output", type=Path, help="firmware output directory")
	args = parser.parse_args()

	try:
		image = args.image.read_bytes()
		if hashlib.sha256(image).hexdigest() != SOURCE_SHA256:
			parser.error("source SHA-256 mismatch; offsets only apply to the documented image")

		# Validate all destinations before writing any firmware.
		for name, offset, size in FIRMWARE:
			target = args.output / name
			if offset + size > len(image):
				parser.error(f"truncated firmware: {name}")
			if target.exists() and target.read_bytes() != image[offset:offset + size]:
				parser.error(f"refusing to overwrite different firmware: {target}")

		args.output.mkdir(parents=True, exist_ok=True)
		for name, offset, size in FIRMWARE:
			data = image[offset:offset + size]
			target = args.output / name
			if not target.exists():
				with target.open("xb") as stream:
					stream.write(data)
			print(f"{hashlib.sha256(data).hexdigest()}  {target}")
	except OSError as error:
		parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
	main()
