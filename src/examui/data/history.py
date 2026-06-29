# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_enrollments(
  history_dir: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, set[str]]]:
  """Read all iscrizioni XLS files.

  Returns (mat2email, email2mat, names, enrollments) where:
  - mat2email: {matricola: email_username}
  - email2mat: {email_username: matricola}
  - names: {email_username: "Cognome Nome"}
  - enrollments: {email_username: set of date strings (YYMMDD)}
  """
  mat2email: dict[str, str] = {}
  email2mat: dict[str, str] = {}
  names: dict[str, str] = {}
  enrollments: dict[str, set[str]] = {}

  for xls in sorted((history_dir / 'iscrizioni').glob('*.xls')):
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

  return mat2email, email2mat, names, enrollments


def read_verbali(
  history_dir: Path, course_name: str
) -> list[tuple[str, str, str, str, str]]:
  """Read all verbali XLS files for a given course.

  Returns list of (matricola, date_YYMMDD, voto_str, stato_str, name) tuples.
  Only rows matching course_name (case-insensitive) are included.
  """
  rows: list[tuple[str, str, str, str, str]] = []
  for xls in sorted((history_dir / 'verbali').glob('*.xls')):
    df = pd.read_excel(xls, header=0)
    matching = df[df['Descrizione insegnamento'].str.casefold() == course_name.casefold()]
    for _, row in matching.iterrows():
      rows.append((
        str(row['Matricola']).strip(),
        row['Data appello'].strftime('%y%m%d'),
        str(row['Voto']),
        str(row['Stato Esito']),
        str(row.get('Nominativo studente', '')).strip(),
      ))
  return rows


def enrolled_emails(history_dir: Path, exam_date: str) -> frozenset[str]:
  """Return the set of email usernames enrolled for a specific exam date."""
  xls_path = history_dir / 'iscrizioni' / f'{exam_date}.xls'
  if not xls_path.exists():
    return frozenset()
  df = pd.read_excel(xls_path, header=0)
  return frozenset(str(e).split('@')[0] for e in df['Email'])
