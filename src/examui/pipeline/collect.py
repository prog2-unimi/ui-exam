# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from examui.data.history import enrolled_emails, read_enrollments, read_verbali
from examui.pipeline import db

_log = logging.getLogger(__name__)

_MARKS_COLUMNS = [
  'mark', 'note', 'email', 'regnum', 'tests', 'javadoc', 'cyclic',
  'code', 'docs', 'file', 'ccode', 'cfile', 'date', 'upload',
  'num', 'first', 'rej', 'acc', 'other',
]


def load_history(
  conn: sqlite3.Connection,
  exam_date: str,
  history_dir: Path,
  course_name: str,
) -> int:
  mat2email, email2mat, names, enrollments = read_enrollments(history_dir)
  verbali_rows = read_verbali(history_dir, course_name)
  enrolled = enrolled_emails(history_dir, exam_date)

  merged: dict[str, dict] = {}
  for mat, date_str, voto, stato, _name in verbali_rows:
    email = mat2email.get(mat)
    if not email:
      continue
    code = voto[:2].upper() + stato[:1].upper()
    merged.setdefault(email, {'matricola': email2mat.get(email, ''), 'appelli': set()})
    merged[email]['appelli'].add(f'{date_str}-{code}')

  for email in enrolled:
    if email not in merged:
      merged[email] = {'matricola': email2mat.get(email, ''), 'appelli': set()}
    if email in enrollments:
      for d in enrollments[email]:
        entry = f'{d}-AS'
        if not any(a.startswith(d) and not a.endswith('-AS') for a in merged[email]['appelli']):
          merged[email]['appelli'].add(entry)

  db.clear_table(conn, 'history')
  count = 0
  for email, data in merged.items():
    if email not in enrolled:
      continue
    appelli = data['appelli'] - {f'{exam_date}-AS'}
    accepted_set = {a for a in appelli if a[-1] == 'V' and not a.split('-')[1].startswith('R')}
    rejected_set = {a for a in appelli if a[-1] == 'R'}
    other_set = appelli - accepted_set - rejected_set

    dates = [a[:6] for a in appelli]
    real_dates = [a[:6] for a in appelli if not a.endswith('-AS')]

    db.upsert_history(
      conn,
      email=email,
      matricola=data['matricola'],
      num=len(appelli),
      first_date=min(real_dates) if real_dates else '',
      first_real=min(real_dates) if real_dates else '',
      last_date=max(dates) if dates else '',
      rejected=':'.join(sorted(rejected_set, reverse=True)),
      accepted=next(iter(accepted_set), ''),
      other=':'.join(sorted(other_set, reverse=True)),
    )
    count += 1

  _log.info('Loaded history for %d students', count)
  return count


def collect_marks(
  conn: sqlite3.Connection,
  exam_date: str,
  evals_dir: Path,
) -> Path:
  computed = {r['email']: r for r in db.all_computed(conn)}
  calendar = {r['email']: r for r in db.all_calendar(conn)}
  uploads = {r['email']: r for r in db.all_uploads(conn)}
  history = {r['email']: r for r in db.all_history(conn)}

  all_emails = set(computed.keys()) | set(uploads.keys())

  rows = []
  for email in sorted(all_emails):
    c = computed.get(email, {})
    if not c.get('tests_status'):
      continue

    h = history.get(email, {})
    cal = calendar.get(email, {})
    up = uploads.get(email, {})

    rows.append({
      'mark': '',
      'note': '',
      'email': email,
      'regnum': h.get('matricola', ''),
      'tests': c.get('tests_status', ''),
      'javadoc': c.get('javadoc_status', ''),
      'cyclic': c.get('javadoc_cyclic', 'NO'),
      'code': c.get('sloc_code', 0),
      'docs': c.get('sloc_docs', 0),
      'file': c.get('sloc_files', 0),
      'ccode': c.get('slocc_code', 0),
      'cfile': c.get('slocc_files', 0),
      'date': cal.get('slot_date', ''),
      'upload': up.get('upload_date', ''),
      'num': h.get('num', 0),
      'first': h.get('first_real', ''),
      'rej': h.get('rejected', ''),
      'acc': h.get('accepted', ''),
      'other': h.get('other', ''),
    })

  new_df = pd.DataFrame(rows, columns=_MARKS_COLUMNS)

  marks_path = evals_dir / exam_date / 'marks.tsv'
  marks_path.parent.mkdir(parents=True, exist_ok=True)
  (marks_path.parent / 'notes').mkdir(exist_ok=True)

  if marks_path.exists():
    _log.info('Merging with existing marks.tsv')
    prev = pd.read_csv(marks_path, sep='\t', na_filter=False)
    marks_path.rename(marks_path.with_suffix('.tsv~'))

    prev_marks = prev[['email', 'mark', 'note']].set_index('email')
    new_df = new_df.set_index('email')
    new_df['mark'] = prev_marks['mark'].reindex(new_df.index).fillna('')
    new_df['note'] = prev_marks['note'].reindex(new_df.index).fillna('')
    new_df = new_df.reset_index()
    new_df = new_df[_MARKS_COLUMNS]

  new_df.sort_values('date').to_csv(marks_path, sep='\t', index=False)
  _log.info('Wrote %s (%d rows)', marks_path, len(new_df))
  return marks_path


def noshow_emails(
  conn: sqlite3.Connection,
) -> list[str]:
  history = {r['email'] for r in db.all_history(conn)}
  computed = {r['email'] for r in db.all_computed(conn)}
  return sorted(history - computed)
