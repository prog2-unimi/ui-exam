# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import tomllib
from datetime import datetime
from os import environ
from pathlib import Path

TODAY = environ.get('TODAY', datetime.now().strftime('%y%m%d'))

def now() -> datetime:
  override = environ.get('NOW')
  if override:
    return datetime.strptime(TODAY + override, '%y%m%d%H%M')
  return datetime.now()

with open(environ['EXAMUI_CONFIG'], 'rb') as _f:
  _cfg = tomllib.load(_f)

HISTORY_DIR      = Path(_cfg['paths']['history_dir'])
EVALS_DIR        = Path(_cfg['paths']['evals_dir'])
STUDENT_BASE     = Path(_cfg['paths']['student_base'])
SLOT_MINUTES     = _cfg['exam']['slot_minutes']
TRIVIAL_PACKAGES = frozenset(_cfg['exam'].get('trivial_packages', ['client', 'clients', 'util', 'utils']))
COURSE_NAME      = _cfg['exam']['course_name']
COURSE_DEGREE    = _cfg['exam'].get('course_degree', '')
TEACHER_EMAIL    = _cfg['actions']['teacher_email']
TEACHER_NAME     = _cfg['actions']['teacher_name']
SUBJECT_PREFIX   = _cfg['actions'].get('subject_prefix', '')
EMAIL_DOMAIN     = _cfg['actions'].get('email_domain', '')
TITOLI           = _cfg['actions'].get('titoli', ['lo studente', 'la studentessa', 'il dottore', 'la dottoressa'])
VSCODE_TUNNEL    = _cfg.get('vscode', {}).get('tunnel')
