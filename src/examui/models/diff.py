# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from examui import config
from examui.data import diff as _diff
from examui.models import source as _source

_OLD_DATE_RE = re.compile(r'^\d{6}$')


def past_sessions(email: str) -> list[str]:
  """Archived session dates (most recent first) where email has a submission."""
  return _diff.list_sessions_with_submission(config.BACKUP_DIR, email)


def _cache_dir(email: str, old_date: str) -> Path:
  return config.WORK_DIR / 'diffcache' / email / old_date


def _ensure_old_root(email: str, old_date: str) -> tuple[Path, bool]:
  """Materialize (once, cached on disk under work_dir) the tree for a past
  submission. Returns (root, raw): raw is True when no project template is
  archived for old_date, so the comparison falls back to unformatted source.
  """
  if not _OLD_DATE_RE.match(old_date):
    raise ValueError(f'Invalid session date: {old_date!r}')
  cache_dir = _cache_dir(email, old_date)
  root = cache_dir / 'source'
  raw_marker = cache_dir / '.raw'
  if root.exists():
    return root, raw_marker.exists()

  cache_dir.mkdir(parents=True, exist_ok=True)
  consegna = cache_dir / 'consegna.zip'
  _diff.extract_backup_consegna(config.BACKUP_DIR, old_date, email, None, consegna)

  template = config.PROJECTS_DIR / f'{old_date}.zip'
  raw = not template.exists()
  _diff.materialize_consegna(consegna, root, cache_dir / 'scratch', email, None if raw else template)
  if raw:
    raw_marker.touch()
  return root, raw


def _current_root(email: str) -> Path:
  base = config.STUDENT_BASE / email / 'source'
  return _diff.source_root(base) if base.exists() else base


@cache
def status(email: str, old_date: str) -> dict:
  """Classify the student's current source against an archived past session."""
  old_root, raw = _ensure_old_root(email, old_date)
  _, _, added, removed, modified = _diff.classify_files(old_root, _current_root(email))
  return {'added': added, 'removed': removed, 'modified': modified, 'raw': raw}


def _linenos_and_content(text: str) -> tuple[list[int], list[str]]:
  """Non-blank lines only, paired with their 1-based line number in the original text."""
  linenos, content = [], []
  for i, line in enumerate(text.splitlines()):
    if line.strip():
      linenos.append(i + 1)
      content.append(line)
  return linenos, content


@cache
def file_rows(email: str, old_date: str, relpath: str) -> dict | None:
  """Row-aligned, syntax-highlighted side-by-side diff data for one file.

  Reuses the same Pygments highlighting as the normal single-file view
  (`source.highlight_lines`) instead of a separately-styled diff library, so
  the diff view looks native rather than like a different tool bolted on.
  Returns {'rows': [...]} — see `data.diff.align_lines` for row shapes; here
  each row additionally carries oldHtml/newHtml (highlighted line content) in
  place of the raw old_no/new_no, or None if not applicable.
  """
  old_root, _ = _ensure_old_root(email, old_date)
  new_root = _current_root(email)
  old_path = (old_root / relpath).resolve()
  new_path = (new_root / relpath).resolve()
  if not str(old_path).startswith(str(old_root.resolve()) + '/'):
    return None
  if not str(new_path).startswith(str(new_root.resolve()) + '/'):
    return None
  if not old_path.is_file() or not new_path.is_file():
    return None

  old_text = old_path.read_text(errors='replace')
  new_text = new_path.read_text(errors='replace')
  old_linenos, old_content = _linenos_and_content(old_text)
  new_linenos, new_content = _linenos_and_content(new_text)
  old_html = _source.highlight_lines(old_text)
  new_html = _source.highlight_lines(new_text)

  rows = []
  for row in _diff.align_lines(old_content, new_content):
    if row['kind'] == 'skip':
      rows.append(row)
      continue
    old_no = old_linenos[row['old_no'] - 1] if row['old_no'] else None
    new_no = new_linenos[row['new_no'] - 1] if row['new_no'] else None
    rows.append({
      'kind': row['kind'],
      'oldNo': old_no, 'oldHtml': old_html[old_no - 1] if old_no else None,
      'newNo': new_no, 'newHtml': new_html[new_no - 1] if new_no else None,
    })
  return {'rows': rows}
