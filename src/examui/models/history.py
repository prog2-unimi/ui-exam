# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import pandas as pd

from examui import config


@dataclass(frozen=True)
class ExamEvent:
    date: str
    mark: str        # 'AS' | 'RI?' | 'RE?' | '19V' | '19R' | ...
    note: str | None


@dataclass(frozen=True)
class Metrics:
    tests:   str   # 'SUCCESS' | 'FAILURE'
    javadoc: str   # 'SUCCESS' | 'FAILURE'
    cyclic:  str   # 'YES' | 'NO'
    code:    int
    docs:    int
    file:    int
    ccode:   int
    cfile:   int
    slot:    str   # 'YYMMDD-HHMM' or '' (the `date` column — booked oral slot)
    upload:  str   # 'YYMMDD-HHMM' or ''
    num:     int


class AbsentCurrentExamEvent:
    """Enrolled in current exam but no source turned in — immutable."""

    def __init__(self, date: str) -> None:
        self.date = date

    @property
    def mark(self) -> str:
        return 'AS'

    @mark.setter
    def mark(self, value: str) -> None:
        raise AttributeError('No source turned in')

    @property
    def short_note(self) -> str:
        return ''

    @short_note.setter
    def short_note(self, value: str) -> None:
        raise AttributeError('No source turned in')

    @property
    def long_note(self) -> str:
        return ''

    @long_note.setter
    def long_note(self, text: str) -> None:
        raise AttributeError('No source turned in')


class LiveCurrentExamEvent:
    """Enrolled in current exam with source turned in — reads/writes live."""

    def __init__(self, email: str, date: str, row: dict) -> None:
        self._email = email
        self.date   = date
        self.metrics = Metrics(
            tests=str(row.get('tests', '')),
            javadoc=str(row.get('javadoc', '')),
            cyclic=str(row.get('cyclic', '')),
            code=int(row.get('code', 0) or 0),
            docs=int(row.get('docs', 0) or 0),
            file=int(row.get('file', 0) or 0),
            ccode=int(row.get('ccode', 0) or 0),
            cfile=int(row.get('cfile', 0) or 0),
            slot=str(row.get('date', '')),
            upload=str(row.get('upload', '')),
            num=int(row.get('num', 0) or 0),
        )

    @property
    def mark(self) -> str:
        path = _marks_path()
        if not path.exists():
            return '??'
        df  = pd.read_csv(path, sep='\t', na_filter=False)
        row = df[df['email'] == self._email]
        if row.empty:
            raise RuntimeError(f'{self._email} not in marks.tsv')
        return str(row.iloc[0]['mark'])

    @mark.setter
    def mark(self, value: str) -> None:
        _update_marks_tsv(self._email, mark=value)

    @property
    def short_note(self) -> str:
        path = _marks_path()
        if not path.exists():
            return ''
        df  = pd.read_csv(path, sep='\t', na_filter=False)
        row = df[df['email'] == self._email]
        if row.empty:
            raise RuntimeError(f'{self._email} not in marks.tsv')
        return str(row.iloc[0]['note'])

    @short_note.setter
    def short_note(self, value: str) -> None:
        _update_marks_tsv(self._email, short_note=value)

    @property
    def long_note(self) -> str:
        p = _long_note_path(self._email)
        return p.read_text() if p.exists() else ''

    @long_note.setter
    def long_note(self, text: str) -> None:
        p       = _long_note_path(self._email)
        cleaned = '\n'.join(l for l in text.splitlines() if not l.startswith('#')).strip()
        if cleaned:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(cleaned)
        elif p.exists():
            p.unlink()


@dataclass(frozen=True)
class Student:
    email:     str
    matricola: str
    name:      str
    events:    list[ExamEvent] = field(default_factory=list)
    current:   AbsentCurrentExamEvent | LiveCurrentExamEvent | None = None

    @property
    def verbali_mark(self) -> dict | None:
        passing = next((e for e in self.events if e.mark[-1:] == 'V'), None)
        if passing:
            return {'value': passing.mark[:-1], 'kind': 'pass'}
        tilde = next(
            (e for e in self.events
             if e.mark[-1:] == 'R' and e.mark[:2] not in ('RI', 'RE')),
            None,
        )
        if tilde:
            return {'value': tilde.mark[:-1] + '~', 'kind': 'tilde'}
        last = next(
            (e for e in self.events if e.mark[:2] in ('RE', 'RI')),
            None,
        )
        if last:
            return {'value': last.mark[:2], 'kind': last.mark[:2]}
        return None


@cache
def exam_date() -> str:
    """Date of the most recent exam, derived from the latest iscrizioni XLS stem (YYMMDD)."""
    files = sorted((config.HISTORY_DIR / 'iscrizioni').glob('*.xls'))
    if not files:
        raise RuntimeError(f'No iscrizioni XLS files found in {config.HISTORY_DIR}/iscrizioni')
    return files[-1].stem


def _marks_path() -> Path:
    return config.EVALS_DIR / exam_date() / 'marks.tsv'


def _long_note_path(email: str) -> Path:
    return config.EVALS_DIR / exam_date() / 'notes' / f'{email}.md'


def _update_marks_tsv(email: str, *, mark: str | None = None, short_note: str | None = None) -> None:
    path = _marks_path()
    if not path.exists():
        raise RuntimeError(f'marks.tsv not found at {path} — exam not yet prepared')
    df = pd.read_csv(path, sep='\t', na_filter=False)
    if email not in df['email'].values:
        raise RuntimeError(f'{email} not in marks.tsv')
    if mark is not None:
        df.loc[df['email'] == email, 'mark'] = mark
    if short_note is not None:
        df.loc[df['email'] == email, 'note'] = short_note
    df.to_csv(path, sep='\t', index=False)


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
    marks_path = _marks_path()
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
