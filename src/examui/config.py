# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from datetime import datetime
from os import environ
from pathlib import Path

TODAY = environ.get('TODAY', datetime.now().strftime('%y%m%d'))

def now() -> datetime:
  override = environ.get('NOW')
  if override:
    return datetime.strptime(TODAY + override, '%y%m%d%H%M')
  return datetime.now()
HISTORY_DIR = Path(environ['HISTORY_DIR'])
EVALS_DIR = Path(environ['EVALS_DIR'])
STUDENT_BASE = Path(environ['STUDENT_BASE'])
SLOT_MINUTES = int(environ.get('SLOT_MINUTES', 30))

# Directories excluded from symbol index and dependency graph.
# Add exam-specific supporting packages here.
TRIVIAL_PACKAGES: frozenset[str] = frozenset({'client', 'clients', 'util', 'utils'})
