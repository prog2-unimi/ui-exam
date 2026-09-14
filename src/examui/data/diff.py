# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import difflib
import re
import shutil
from pathlib import Path
from zipfile import ZipFile

from examui.data.extraction import extract_source

_CONSEGNA_RE = re.compile(r'^(?P<email>[^/@]+)@[^/]+/(?P<attempt>\d+)-consegna\.zip$')


def source_root(base: Path) -> Path:
  java = base / 'src' / 'main' / 'java'
  return java if java.exists() else base


def _consegna_entries(zf: ZipFile, email: str) -> dict[int, str]:
  entries = {}
  for name in zf.namelist():
    m = _CONSEGNA_RE.match(name)
    if m and m.group('email') == email:
      entries[int(m.group('attempt'))] = name
  return entries


def extract_backup_consegna(
  backup_dir: Path, old_date: str, email: str, attempt: int | None, dest: Path
) -> int:
  """Extract one numbered consegna.zip for a student out of an archived session zip.

  Returns the attempt number actually used (the last one, if `attempt` is None).
  """
  backup_zip = backup_dir / f'{old_date}.zip'
  if not backup_zip.exists():
    raise FileNotFoundError(f'No backup archive for session {old_date}: {backup_zip}')

  with ZipFile(backup_zip) as zf:
    entries = _consegna_entries(zf, email)
    if not entries:
      raise FileNotFoundError(f'No submission by {email} in backup session {old_date}')
    if attempt is None:
      attempt = max(entries)
    elif attempt not in entries:
      available = ', '.join(str(a) for a in sorted(entries))
      raise ValueError(f'{email} has no attempt {attempt} in session {old_date} (available: {available})')
    dest.write_bytes(zf.read(entries[attempt]))
  return attempt


def list_sessions_with_submission(backup_dir: Path, email: str) -> list[str]:
  """All archived session dates (most recent first) where email has a submission."""
  dates = sorted((p.stem for p in backup_dir.glob('*.zip')), reverse=True)
  found = []
  for old_date in dates:
    with ZipFile(backup_dir / f'{old_date}.zip') as zf:
      if _consegna_entries(zf, email):
        found.append(old_date)
  return found


def materialize_consegna(
  consegna: Path, final_dir: Path, scratch_dir: Path, email: str, template: Path | None
) -> None:
  """Extract a consegna.zip into final_dir, as a plain java tree.

  If `template` is given, overlays consegna onto that project template and
  runs spotlessApply first (in scratch_dir), then copies just the resulting
  java source root into final_dir — so final_dir always ends up as a bare
  package tree, whether or not formatting was applied.
  """
  if template is None:
    final_dir.mkdir()
    with ZipFile(consegna) as zf:
      zf.extractall(final_dir)
    return
  root = source_root(extract_source(email, consegna, template, scratch_dir))
  shutil.copytree(root, final_dir)


def _relative_files(root: Path) -> dict[str, Path]:
  return {str(p.relative_to(root)): p for p in root.rglob('*') if p.is_file()}


def _nonblank_lines(path: Path) -> list[str]:
  return [line for line in path.read_text(errors='replace').splitlines() if line.strip()]


def align_lines(old_lines: list[str], new_lines: list[str], context: int = 2) -> list[dict]:
  """Line-level alignment between two line sequences, collapsing long unchanged
  runs to `context` lines on each side of a change.

  Returns row dicts, each either {'kind': 'equal'|'delete'|'insert'|'replace',
  'old_no': int|None, 'new_no': int|None} (1-based indices into old_lines/
  new_lines) or {'kind': 'skip', 'count': int} for a collapsed unchanged run.
  Pure line-content alignment — callers decide what "line" means (e.g. whether
  blank lines were filtered out beforehand) and what to render for each index.
  """
  opcodes = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes()
  rows: list[dict] = []
  for idx, (op, i1, i2, j1, j2) in enumerate(opcodes):
    if op == 'equal':
      length = i2 - i1
      head = 0 if idx == 0 else context
      tail = 0 if idx == len(opcodes) - 1 else context
      if length <= head + tail:
        rows += [{'kind': 'equal', 'old_no': i1 + k + 1, 'new_no': j1 + k + 1} for k in range(length)]
      else:
        rows += [{'kind': 'equal', 'old_no': i1 + k + 1, 'new_no': j1 + k + 1} for k in range(head)]
        rows.append({'kind': 'skip', 'count': length - head - tail})
        rows += [{'kind': 'equal', 'old_no': i1 + k + 1, 'new_no': j1 + k + 1} for k in range(length - tail, length)]
    elif op == 'delete':
      rows += [{'kind': 'delete', 'old_no': k + 1, 'new_no': None} for k in range(i1, i2)]
    elif op == 'insert':
      rows += [{'kind': 'insert', 'old_no': None, 'new_no': k + 1} for k in range(j1, j2)]
    elif op == 'replace':
      for k in range(max(i2 - i1, j2 - j1)):
        rows.append({
          'kind': 'replace',
          'old_no': i1 + k + 1 if i1 + k < i2 else None,
          'new_no': j1 + k + 1 if j1 + k < j2 else None,
        })
  return rows


def classify_files(
  old_root: Path, new_root: Path
) -> tuple[dict[str, Path], dict[str, Path], list[str], list[str], list[str]]:
  """Compare two source trees, ignoring blank-line-only differences.

  Returns (old_files, new_files, added, removed, modified): the two
  relpath -> Path maps, plus sorted relpath lists for files only in
  new_root, only in old_root, and present in both with different
  (non-blank) content.
  """
  old_files = _relative_files(old_root)
  new_files = _relative_files(new_root)
  added = sorted(new_files.keys() - old_files.keys())
  removed = sorted(old_files.keys() - new_files.keys())
  modified = [
    rel for rel in sorted(old_files.keys() & new_files.keys())
    if _nonblank_lines(old_files[rel]) != _nonblank_lines(new_files[rel])
  ]
  return old_files, new_files, added, removed, modified
