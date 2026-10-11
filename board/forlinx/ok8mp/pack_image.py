#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Package in-tree OK8MP U-Boot and TF-A outputs using the compiled Binman layout."""
from pathlib import Path
import argparse
import hashlib
import shutil
import json
import os
import struct
import re
import subprocess

build = Path(__file__).resolve().parents[3]
workspace = build.parent
firmware = workspace / 'firmware/firmware-imx-8.10/firmware/ddr/synopsys'
bl31 = workspace / 'atf/build/imx8mp/release/bl31.bin'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=workspace / 'output/boot',
	help='directory for the final image and packaging metadata')
out = parser.parse_args().output.resolve()
out.mkdir(parents=True, exist_ok=True)
dtb = build / 'u-boot.dtb'
mkimage = build / 'tools/mkimage'

def prop(node, name, kind='s'):
	return subprocess.check_output(['fdtget', '-t' + kind, str(dtb), node, name], text=True).strip()

def integer(node, name):
	return int(prop(node, name, 'x'), 16)

def run(*args):
	subprocess.run([str(arg) for arg in args], check=True, cwd=out, env={**os.environ, 'PATH':
		str(build / 'scripts/dtc') + os.pathsep + os.environ['PATH']})

splnode = '/binman/section/nxp-imx8mimage'
fitnode = '/binman/section/fit'
confnode = fitnode + '/configurations/@config-SEQ'
assert prop(confnode, 'firmware') == 'atf', 'FIT firmware must select BL31'
assert prop(confnode, 'loadables') == 'uboot', 'FIT loadables must select U-Boot'
assert prop(fitnode + '/images/atf', 'os') == 'arm-trusted-firmware'
assert prop(fitnode + '/images/uboot', 'os') == 'u-boot'
loader = integer(splnode, 'nxp,loader-address')
fit_offset = integer(fitnode, 'offset')
external = integer(fitnode, 'fit,external-offset')
spl = (build / 'spl/u-boot-spl.bin').read_bytes()
spl_dtb = (build / 'spl/u-boot-spl.dtb').read_bytes()
assert spl.endswith(spl_dtb)
symbols = {}
for line in (build / 'spl/u-boot-spl.sym').read_text().splitlines():
	parts = line.split()
	if parts and parts[-1] in ('_end', '_binman_sym_magic', '__bss_start', '__bss_end'):
		symbols[parts[-1]] = int(parts[0], 16)
assert symbols['_end'] - loader + len(spl_dtb) == len(spl)
magic_offset = symbols['_binman_sym_magic'] - loader
assert struct.unpack_from('<Q', spl, magic_offset)[0] == 0
payload = bytearray(spl)
payload.extend(bytes((-len(payload)) % 4))
components = [build / 'spl/u-boot-spl.bin', build / 'u-boot.bin', build / 'u-boot-nodtb.bin', dtb, bl31]
inputs = list(components)
checksum_file = firmware / 'SHA256SUMS'
try:
	checksums = {name: digest for digest, name in
		(line.split() for line in checksum_file.read_text().splitlines())}
except (OSError, ValueError) as error:
	parser.error(f'invalid firmware checksum file: {error}')
expected_names = {f'lpddr4_pmu_train_{mode}_{mem}_202006.bin'
	for mode in ('1d', '2d') for mem in ('imem', 'dmem')}
if set(checksums) != expected_names:
	parser.error('SHA256SUMS must identify the four official LPDDR4 202006 firmware files')
inputs.append(checksum_file)
padded_firmware = []
for mode in ('1d', '2d'):
	for mem, size in (('imem', 0x8000), ('dmem', 0x4000)):
		name = prop(splnode + '/section/ddr-' + mode + '-' + mem + '-fw', 'filename')
		if Path(name).name != name:
			parser.error(f'invalid padded firmware filename in DT: {name}')
		path = firmware / f'lpddr4_pmu_train_{mode}_{mem}_202006.bin'
		try:
			data = path.read_bytes()
		except OSError as error:
			parser.error(str(error))
		if not data or len(data) > size:
			parser.error(f'invalid firmware size: {path}')
		if hashlib.sha256(data).hexdigest() != checksums[path.name]:
			parser.error(f'firmware SHA-256 mismatch: {path}')
		# Preserve official blobs; the SPL loader expects fixed-size IMEM/DMEM windows.
		data = data.ljust(size, b'\0')
		payload.extend(data)
		padded_firmware.append((out / 'ddr-firmware' / name, data))
		inputs.append(path)
config = dict(line.split('=', 1) for line in (build / '.config').read_text().splitlines()
	if line.startswith('CONFIG_') and '=' in line)
assert config.get('CONFIG_SPL_ATF') == 'y', 'SPL must enable ATF handoff'
assert config.get('CONFIG_SPL_ATF_LOAD_IMAGE_V2') == 'y', 'TF-A requires V2 handoff parameters'
assert config.get('CONFIG_SPL_FIT_IMAGE_TINY') != 'y', 'ATF handoff requires full FIT loading'
stack_top = int(config['CONFIG_SPL_STACK'], 0)
heap_size = int(config['CONFIG_SPL_SYS_MALLOC_F_LEN'], 0)
assert stack_top <= integer(fitnode + '/images/atf', 'load'), 'SPL heap overlaps TF-A'
asm_offsets = (build / 'spl/include/generated/generic-asm-offsets.h').read_text()
gd_size = int(re.search(r'#define GENERATED_GBL_DATA_SIZE (\d+)', asm_offsets)[1])
stack_pointer = stack_top - heap_size - gd_size
stack_bottom = stack_pointer - 0x4000
bss_start = int(config['CONFIG_SPL_BSS_START_ADDR'], 0)
bss_limit = bss_start + int(config['CONFIG_SPL_BSS_MAX_SIZE'], 0)
assert symbols['__bss_start'] == bss_start
assert symbols['__bss_end'] <= bss_limit <= stack_bottom, 'SPL BSS overlaps early stack'
# TF-A accepts V2 handoff parameters only from non-secure OCRAM or TCM.
assert 0x900000 <= bss_start < bss_limit <= 0x960000, 'SPL BSS outside TF-A parameter window'
assert loader + len(payload) <= bss_start, 'DDR firmware overlaps SPL BSS'
for path, data in padded_firmware:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_bytes(data)
(out / 'u-boot-spl-ddr.bin').write_bytes(payload)
# LOADER splits on whitespace; mkimage runs in out so a bare filename also supports paths with spaces.
(out / 'imximage.cfg').write_text(f'ROM_VERSION v{integer(splnode, "nxp,rom-version")}\n'
	f'BOOT_FROM {prop(splnode, "nxp,boot-from")}\nLOADER u-boot-spl-ddr.bin {loader:#x}\n')
run(mkimage, '-d', out / 'u-boot-spl-ddr.bin', '-n', out / 'imximage.cfg',
	'-T', 'imx8mimage', out / 'u-boot-spl-mkimage.bin')
its = '/dts-v1/;\n/ {\n\tdescription = "OK8MP-C V3.1 4 GiB";\n\t#address-cells = <1>;\n\timages {\n'
for name, template, path in [('uboot', 'uboot', build / 'u-boot-nodtb.bin'),
		('atf', 'atf', bl31), ('fdt-1', '@fdt-SEQ', dtb)]:
	node = fitnode + '/images/' + template
	its += f'\t\t{name} {{\n\t\t\tdescription = "{name}";\n\t\t\tdata = /incbin/("{path}");\n'
	its += f'\t\t\ttype = "{prop(node, "type")}";\n\t\t\tcompression = "none";\n'
	if name != 'fdt-1':
		its += f'\t\t\tarch = "arm64";\n\t\t\tload = <{integer(node, "load"):#x}>;\n'
		its += f'\t\t\tos = "{prop(node, "os")}";\n'
		its += f'\t\t\tentry = <{integer(node, "entry"):#x}>;\n'
	its += '\t\t\thash { algo = "sha256"; };\n\t\t};\n'
its += '\t};\n\tconfigurations {\n\t\tdefault = "config-1";\n\t\tconfig-1 {\n'
its += '\t\t\tdescription = "imx8mp-ok8mp";\n\t\t\tfdt = "fdt-1";\n'
its += f'\t\t\tfirmware = "{prop(confnode, "firmware")}";\n'
its += f'\t\t\tloadables = "{prop(confnode, "loadables")}";\n\t\t}};\n\t}};\n}};\n'
(out / 'u-boot.its').write_text(its)
run(mkimage, '-E', '-p', hex(external), '-f', out / 'u-boot.its', out / 'u-boot.itb')
header = (out / 'u-boot-spl-mkimage.bin').read_bytes()
assert len(header) <= fit_offset
flash = header.ljust(fit_offset, b'\0') + (out / 'u-boot.itb').read_bytes()
# Validate the ROM entry and payload at the IVT-relative offset.
assert flash[:4] == bytes.fromhex('d1002041')
entry, reserved, dcd, boot_data, ivt_self, csf = struct.unpack_from('<6I', flash, 4)
assert entry == loader
rom_start, rom_size, plugin = struct.unpack_from('<3I', header, boot_data - ivt_self)
assert rom_start + rom_size <= bss_start, 'ROM image overlaps SPL BSS'
print(f'OCRAM layout: ROM end={rom_start + rom_size:#x}, '
	f'BSS=[{bss_start:#x}, {bss_limit:#x}), stack bottom={stack_bottom:#x}, '
	f'SP={stack_pointer:#x}, heap={stack_top - heap_size:#x}')
payload_offset = entry - ivt_self
assert flash[payload_offset:payload_offset + len(payload)] == payload
assert flash[fit_offset:fit_offset + 4] == bytes.fromhex('d00dfeed')
(out / 'flash.bin').write_bytes(flash)
for path in components:
	shutil.copyfile(path, out / path.name)
# Describe all exported boot images, including the raw component binaries.
artifacts = [out / p.name for p in components] + [out / name for name in
	('flash.bin', 'u-boot-spl-ddr.bin', 'u-boot-spl-mkimage.bin', 'u-boot.itb')]
(out / 'SHA256SUMS').write_text(''.join(
	f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in artifacts))
manifest = {'method': 'native mkimage; DDR loader uses checked _end + FDT fallback',
	'fit_offset': fit_offset, 'inputs': {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
	for p in inputs}, 'flash_sha256': hashlib.sha256(flash).hexdigest(), 'flash_size': len(flash)}
shutil.copyfile(build / 'board/forlinx/ok8mp/ram-test.uuu', out / 'ram-test.uuu')
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
