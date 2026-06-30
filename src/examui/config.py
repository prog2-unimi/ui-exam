# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import tomllib
from datetime import datetime
from os import environ
from pathlib import Path

# defaults

TITOLI_DEFAULT = ['lo studente', 'la studentessa', 'il dottore', 'la dottoressa']
TRIVIAL_PACKAGES_DEFAULT = ['client', 'clients', 'util', 'utils']

# date and time

TODAY = environ.get('TODAY', datetime.now().strftime('%y%m%d'))

def now() -> datetime:
  override = environ.get('NOW')
  if override:
    return datetime.strptime(TODAY + override, '%y%m%d%H%M')
  return datetime.now()

_config_path = environ['EXAMUI_CONFIG']

with open(_config_path, 'rb') as _f:
  _cfg = tomllib.load(_f)


class ConfigError(Exception):
  pass


def _get(section: str, key: str, default_value=None):
  try:
    sect = _cfg[section]
  except KeyError:
    raise ConfigError(f'Missing [{section}] section in {_config_path}') from None
  try:
    return sect[key]
  except KeyError:
    if default_value is None:
      raise ConfigError(f'Missing "{key}" in [{section}] section of {_config_path}') from None
    return default_value


# base directories

HISTORY_DIR      = Path(_get('paths', 'history_dir'))
EVALS_DIR        = Path(_get('paths', 'evals_dir'))
WORK_DIR         = Path(_get('paths', 'work_dir'))

# derived directories

STUDENT_BASE     = WORK_DIR / 'student'
PROJECTS_DIR     = HISTORY_DIR / 'projects'

# exam configuration

SLOT_MINUTES     = _get('exam', 'slot_minutes')
COURSE_NAME      = _get('exam', 'course_name')
COURSE_DEGREE    = _get('exam', 'course_degree')

TEACHER_EMAIL    = _get('exam', 'teacher_email')
TEACHER_NAME     = _get('exam', 'teacher_name')
SUBJECT_PREFIX   = _get('exam', 'subject_prefix')
EMAIL_DOMAIN     = _get('exam', 'email_domain')

TITOLI           = _get('exam', 'titoli', TITOLI_DEFAULT)
TRIVIAL_PACKAGES = frozenset(_get('exam', 'trivial_packages', TRIVIAL_PACKAGES_DEFAULT))

# external services

VSCODE_TUNNEL    = _get('vscode', 'tunnel')
CAL_URL          = _get('booking', 'cal_url')
CAL_ENDPOINT     = _get('booking', 'endpoint')
CAL_VERSION      = _get('booking', 'version')
CAL_EVENT        = _get('booking', 'event')
UPLOADS_URL      = _get('uploads', 'url')
UPLOADS_USERNAME = _get('uploads', 'username')
UPLOADS_SESSION  = _get('uploads', 'session')
