# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import dataclasses
from datetime import date, datetime
from functools import cache
from pathlib import Path

import pandas as pd

from examui import config
from examui.models.events import ExamEvent, Mark, Metrics, Student


class UnderEvaluationMark:
  def __init__(self, email: str) -> None:
    self._email = email

  def _marks_path(self) -> Path:
    path = config.EVALS_DIR / exam_date() / 'marks.tsv'
    if not path.exists():
      raise RuntimeError(f'marks.tsv not found at {path}')
    return path

  def _note_path(self) -> Path:
    return config.EVALS_DIR / exam_date() / 'notes' / f'{self._email}.md'

  def _read_tsv(self, field: str) -> str:
    df = pd.read_csv(self._marks_path(), sep='\t', na_filter=False)
    row = df[df['email'] == self._email]
    if row.empty:
      raise RuntimeError(f'{self._email} not in marks.tsv')
    return str(row.iloc[0][field])

  def _write_tsv(self, **kwargs: str) -> None:
    path = self._marks_path()
    df = pd.read_csv(path, sep='\t', na_filter=False)
    if self._email not in df['email'].values:
      raise RuntimeError(f'{self._email} not in marks.tsv')
    for col, val in kwargs.items():
      df.loc[df['email'] == self._email, col] = val
    df.to_csv(path, sep='\t', index=False)

  def _read_md(self) -> str:
    p = self._note_path()
    return p.read_text() if p.exists() else ''

  def _write_md(self, text: str) -> None:
    p = self._note_path()
    cleaned = '\n'.join(line for line in text.splitlines() if not line.startswith('#')).strip()
    if cleaned:
      p.parent.mkdir(parents=True, exist_ok=True)
      p.write_text(cleaned)
    elif p.exists():
      p.unlink()

  @property
  def provisional(self) -> str:
    return self._read_tsv('mark')

  @provisional.setter
  def provisional(self, value: str):
    self._write_tsv(mark=value)

  @property
  def annotation(self) -> str:
    return self._read_tsv('note')

  @annotation.setter
  def annotation(self, value: str):
    self._write_tsv(note=value)

  def save(self, provisional: str, annotation: str) -> None:
    self._write_tsv(mark=provisional, note=annotation)

  @property
  def note(self) -> str:
    return self._read_md()

  @note.setter
  def note(self, text: str):
    self._write_md(text)


class UnderEvaluationEvent:
  """Enrolled in current exam with source turned in — reads/writes live via mark."""

  def __init__(self, email: str, date: date, row: dict) -> None:
    self.date = date
    self.metrics = Metrics.from_row(row)
    self.mark = UnderEvaluationMark(email)


@cache
def exam_date() -> str:
  """Date of the most recent exam, derived from the latest iscrizioni XLS stem (YYMMDD)."""
  files = sorted((config.HISTORY_DIR / 'iscrizioni').glob('*.xls'))
  if not files:
    raise RuntimeError(f'No iscrizioni XLS files found in {config.HISTORY_DIR}/iscrizioni')
  return files[-1].stem


@cache
def all_students() -> dict[str, Student]:
  mat2email: dict[str, str] = {}
  email2mat: dict[str, str] = {}
  names: dict[str, str] = {}
  enrollments: dict[str, set[str]] = {}

  current_date = exam_date()

  # ── iscrizioni ────────────────────────────────────────────────────────────
  for xls in sorted((config.HISTORY_DIR / 'iscrizioni').glob('*.xls')):
    date = xls.stem
    df = pd.read_excel(xls, header=0, converters={'Matricola': str})
    for _, row in df.iterrows():
      mat = str(row['Matricola']).strip()
      if '0000' in mat:
        continue
      email = str(row['Email']).split('@')[0]
      mat2email[mat] = email
      email2mat[email] = mat
      enrollments.setdefault(email, set()).add(date)
      if email not in names and 'Cognome' in df.columns:
        names[email] = f'{row["Cognome"]} {row["Nome"]}'.strip()

  # ── verbali ───────────────────────────────────────────────────────────────
  results: dict[str, dict[str, Mark]] = {}

  for xls in sorted((config.HISTORY_DIR / 'verbali').glob('*.xls')):
    df = pd.read_excel(xls, header=0)
    prog2 = df[df['Descrizione insegnamento'] == 'PROGRAMMAZIONE II']
    for _, row in prog2.iterrows():
      mat = str(row['Matricola']).strip()
      email = mat2email.get(mat)
      if not email:
        continue
      try:
        mark = Mark.from_verbale(str(row['Voto']), str(row['Stato Esito']))
      except ValueError:
        continue
      results.setdefault(email, {})[row['Data appello'].strftime('%y%m%d')] = mark
      if email not in names:
        names[email] = str(row['Nominativo studente']).strip()

  # ── notes (all dates — current-date long notes are still read live) ───────
  notes: dict[str, dict[str, str]] = {}
  for note_file in config.EVALS_DIR.glob('*/notes/*.md'):
    date = note_file.parent.parent.name
    email = note_file.stem
    notes.setdefault(email, {})[date] = note_file.read_text()

  # ── current marks.tsv ─────────────────────────────────────────────────────
  current_rows: dict[str, dict] = {}
  marks_path = config.EVALS_DIR / current_date / 'marks.tsv'
  if marks_path.exists():
    df = pd.read_csv(marks_path, sep='\t', na_filter=False)
    for _, row in df.iterrows():
      current_rows[str(row['email'])] = row.to_dict()

  # ── assemble ──────────────────────────────────────────────────────────────
  all_emails = enrollments.keys() | results.keys() | notes.keys()
  students: dict[str, Student] = {}

  for email in all_emails:
    all_dates = (
      enrollments.get(email, set())
      | set(results.get(email, {}).keys())
      | set(notes.get(email, {}).keys())
    )

    events = []
    for d_str in sorted(all_dates, reverse=True):
      d = datetime.strptime(d_str, '%y%m%d').date()
      if d_str in results.get(email, {}):
        events.append(
          ExamEvent(
            date=d,
            mark=dataclasses.replace(results[email][d_str], note=notes.get(email, {}).get(d_str)),
          )
        )
      elif d_str == current_date and email in current_rows:
        events.append(UnderEvaluationEvent(email, d, current_rows[email]))
      else:
        events.append(ExamEvent(date=d, mark=None))

    students[email] = Student(
      email=email,
      matricola=email2mat.get(email, ''),
      name=names.get(email, ''),
      events=events,
    )

  return students
