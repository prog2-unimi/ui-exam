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
    def note(self) -> str | None:
        return None

    @note.setter
    def note(self, text: str) -> None:
        raise AttributeError('No source turned in')


class LiveCurrentExamEvent:
    """Enrolled in current exam with source turned in — reads/writes live."""

    def __init__(self, email: str, date: str) -> None:
        self._email = email
        self.date   = date

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
        path = _marks_path()
        if not path.exists():
            raise RuntimeError(f'marks.tsv not found at {path} — exam not yet prepared')
        df = pd.read_csv(path, sep='\t', na_filter=False)
        if self._email not in df['email'].values:
            raise RuntimeError(f'{self._email} not in marks.tsv')
        df.loc[df['email'] == self._email, 'mark'] = value
        df.to_csv(path, sep='\t', index=False)

    @property
    def note(self) -> str:
        p = _note_path(self._email)
        return p.read_text() if p.exists() else ''

    @note.setter
    def note(self, text: str) -> None:
        p       = _note_path(self._email)
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
            (e for e in reversed(self.events)
             if e.mark[-1:] == 'R' and e.mark[:2] not in ('RI', 'RE')),
            None,
        )
        if tilde:
            return {'value': tilde.mark[:-1] + '~', 'kind': 'tilde'}
        last = next(
            (e for e in reversed(self.events) if e.mark[:2] in ('RE', 'RI')),
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


def _note_path(email: str) -> Path:
    return config.EVALS_DIR / exam_date() / 'notes' / f'{email}.md'




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

    # ── past notes (current-exam notes are read live) ─────────────────────────
    notes: dict[str, dict[str, str]] = {}
    for note_file in config.EVALS_DIR.glob('*/notes/*.md'):
        date  = note_file.parent.parent.name
        email = note_file.stem
        if date == current_date:
            continue
        notes.setdefault(email, {})[date] = note_file.read_text()

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
            src_base = config.STUDENT_BASE / email / 'source'
            src_java = src_base / 'src' / 'main' / 'java'
            has_src  = (src_java if src_java.exists() else src_base).exists()
            current  = LiveCurrentExamEvent(email, current_date) if has_src else AbsentCurrentExamEvent(current_date)

        students[email] = Student(
            email=email,
            matricola=email2mat.get(email, ''),
            name=names.get(email, ''),
            events=events,
            current=current,
        )

    return students
