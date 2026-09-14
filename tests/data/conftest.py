# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import os
from pathlib import Path

os.environ['EXAMUI_CONFIG'] = str(Path(__file__).parent / 'fixture-config.toml')
