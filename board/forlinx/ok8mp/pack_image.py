#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0+
"""Use the SDK signature packager to provision the SPL verification key."""

import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parents[4]
packager = workspace / 'tools/pack_image.py'
if not packager.is_file() or not (workspace / 'tools/fit_signature.py').is_file():
	sys.exit('Signed OK8MP packaging requires the arm-sdk signature branch')
os.execv(sys.executable, [sys.executable, str(packager), *sys.argv[1:]])
