# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from functools import cache
from pathlib import Path

import pandas as pd

from examui import config
from examui.models.events import AbsentCurrentExamEvent, ExamEvent, Metrics, Student


class LiveCurrentExamEvent:
    """Enrolled in current exam with source turned in — reads/writes live."""

    def __init__(self, email: str, date: str, row: dict) -> None:
        self._email  = email
        self.date    = date
        self.metrics = Metrics.from_row(row)

    def _marks_path(self) -> Path:
        return config.EVALS_DIR / exam_date() / 'marks.tsv'

    def _note_path(self) -> Path:
        return config.EVALS_DIR / exam_date() / 'notes' / f'{self._email}.md'

    def _read_tsv(self, field: str, default: str = '') -> str:
        path = self._marks_path()
        if not path.exists():
            return default
        df  = pd.read_csv(path, sep='\t', na_filter=False)
        row = df[df['email'] == self._email]
        if row.empty:
            raise RuntimeError(f'{self._email} not in marks.tsv')
        return str(row.iloc[0][field])

    def _write_tsv(self, **kwargs: str) -> None:
        path = self._marks_path()
        if not path.exists():
            raise RuntimeError(f'marks.tsv not found at {path} — exam not yet prepared')
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
        p       = self._note_path()
        cleaned = '\n'.join(l for l in text.splitlines() if not l.startswith('#')).strip()
        if cleaned:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(cleaned)
        elif p.exists():
            p.unlink()

    @property
    def mark(self) -> str:        return self._read_tsv('mark', default='??')
    @mark.setter
    def mark(self, value: str):   self._write_tsv(mark=value)

    @property
    def short_note(self) -> str:       return self._read_tsv('note')
    @short_note.setter
    def short_note(self, value: str):  self._write_tsv(note=value)

    @property
    def long_note(self) -> str:        return self._read_md()
    @long_note.setter
    def long_note(self, text: str):    self._write_md(text)


@cache
def exam_date() -> str:
    """Date of the most recent exam, derived from the latest iscrizioni XLS stem (YYMMDD)."""
    files = sorted((config.HISTORY_DIR / 'iscrizioni').glob('*.xls'))
    if not files:
        raise RuntimeError(f'No iscrizioni XLS files found in {config.HISTORY_DIR}/iscrizioni')
    return files[-1].stem


@cache
def all_students() -> dict[str, Student]:
    mat2email:   dict[str, str]      = {}
    email2mat:   dict[str, str]      = {}
    names:       dict[str, str]      = {}
    enrollments: dict[str, set[str]] = {}

    current_date = exam_date()

    # ── iscrizioni ────────────────────────────────────────────────────────────
    for xls in sorted((config.HISTORY_DIR / 'iscrizioni').glob('*.xls')):
        date = xls.stem
        df   = pd.read_excel(xls, header=0, converters={'Matricola': str})
        for _, row in df.iterrows():
            mat = str(row['Matricola']).strip()
            if '0000' in mat:
                continue
            email = str(row['Email']).split('@')[0]
            mat2email[mat]   = email
            email2mat[email] = mat
            enrollments.setdefault(email, set()).add(date)
            if email not in names and 'Cognome' in df.columns:
                names[email] = f"{row['Cognome']} {row['Nome']}".strip()

    # ── verbali ───────────────────────────────────────────────────────────────
    results: dict[str, dict[str, str]] = {}

    for xls in sorted((config.HISTORY_DIR / 'verbali').glob('*.xls')):
        df    = pd.read_excel(xls, header=0)
        prog2 = df[df['Descrizione insegnamento'] == 'PROGRAMMAZIONE II']
        for _, row in prog2.iterrows():
            mat   = str(row['Matricola']).strip()
            email = mat2email.get(mat)
            if not email:
                continue
            mark = str(row['Voto'])[:2].upper() + str(row['Stato Esito'])[:1]
            results.setdefault(email, {})[row['Data appello'].strftime('%y%m%d')] = mark
            if email not in names:
                names[email] = str(row['Nominativo studente']).strip()

    # ── past notes (current-exam long notes are read live) ────────────────────
    notes: dict[str, dict[str, str]] = {}
    for note_file in config.EVALS_DIR.glob('*/notes/*.md'):
        date  = note_file.parent.parent.name
        email = note_file.stem
        if date == current_date:
            continue
        notes.setdefault(email, {})[date] = note_file.read_text()

    # ── current marks.tsv → determines who has source ─────────────────────────
    current_rows: dict[str, dict] = {}
    marks_path = config.EVALS_DIR / exam_date() / 'marks.tsv'
    if marks_path.exists():
        df = pd.read_csv(marks_path, sep='\t', na_filter=False)
        for _, row in df.iterrows():
            current_rows[str(row['email'])] = row.to_dict()

    # ── assemble ──────────────────────────────────────────────────────────────
    all_emails = enrollments.keys() | results.keys() | notes.keys()
    students: dict[str, Student] = {}

    for email in all_emails:
        past_dates = (
            (enrollments.get(email, set()) | set(results.get(email, {}).keys()) | set(notes.get(email, {}).keys()))
            - {current_date}
        )
        events = [
            ExamEvent(
                date=date,
                mark=results.get(email, {}).get(date, 'AS'),
                note=notes.get(email, {}).get(date),
            )
            for date in sorted(past_dates, reverse=True)
        ]

        current = None
        if current_date in enrollments.get(email, set()):
            if email in current_rows:
                current = LiveCurrentExamEvent(email, current_date, current_rows[email])
            else:
                current = AbsentCurrentExamEvent(current_date)

        students[email] = Student(
            email=email,
            matricola=email2mat.get(email, ''),
            name=names.get(email, ''),
            events=events,
            current=current,
        )

    return students
