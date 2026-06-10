# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from datetime import datetime
from os import environ
from pathlib import Path

EXAM_DAY     = environ.get('EXAM_DAY', datetime.now().strftime('%y%m%d'))
HISTORY_DIR  = Path(environ['HISTORY_DIR'])
EVALS_DIR    = Path(environ['EVALS_DIR'])
STUDENT_BASE = Path(environ['STUDENT_BASE'])
SLOT_MINUTES = int(environ.get('SLOT_MINUTES', 30))
