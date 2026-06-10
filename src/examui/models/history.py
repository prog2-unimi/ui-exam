# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from dataclasses import dataclass, field

import pandas as pd

from examui import config


@dataclass
class ExamEvent:
    date: str       # YYMMDD
    risultato: str  # "AS" | "RI?" | "RE?" | "19V" | "19R" | ...
    note: str | None


@dataclass
class Student:
    email: str
    matricola: str
    name: str
    events: list[ExamEvent] = field(default_factory=list)  # descending by date


_cache: dict[str, Student] | None = None


def all_students() -> dict[str, Student]:
    global _cache
    if _cache is None:
        _cache = _build()
    return _cache


def _build() -> dict[str, Student]:
    mat2email:   dict[str, str]      = {}
    email2mat:   dict[str, str]      = {}
    names:       dict[str, str]      = {}   # email → display name
    enrollments: dict[str, set[str]] = {}   # email → {date}

    # ── iscrizioni ────────────────────────────────────────────────────────────
    for xls in sorted((config.HISTORY_DIR / 'iscrizioni').glob('*.xls')):
        date = xls.stem
        df = pd.read_excel(xls, header=0, converters={'Matricola': str})
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
    # risultato = voto[:2].upper() + stato[:1]  (mirrors get_history in Snakefile)
    results: dict[str, dict[str, str]] = {}  # email → {date → risultato}

    for xls in sorted((config.HISTORY_DIR / 'verbali').glob('*.xls')):
        df = pd.read_excel(xls, header=0)
        prog2 = df[df['Descrizione insegnamento'] == 'PROGRAMMAZIONE II']
        for _, row in prog2.iterrows():
            mat   = str(row['Matricola']).strip()
            email = mat2email.get(mat)
            if not email:
                continue
            risultato = str(row['Voto'])[:2].upper() + str(row['Stato Esito'])[:1]
            results.setdefault(email, {})[row['Data appello'].strftime('%y%m%d')] = risultato
            if email not in names:
                names[email] = str(row['Nominativo studente']).strip()

    # ── notes ─────────────────────────────────────────────────────────────────
    notes: dict[str, dict[str, str]] = {}  # email → {date → text}
    for note_file in config.EVALS_DIR.glob('*/notes/*.md'):
        date  = note_file.parent.parent.name
        email = note_file.stem
        notes.setdefault(email, {})[date] = note_file.read_text()

    # ── assemble ──────────────────────────────────────────────────────────────
    all_emails = enrollments.keys() | results.keys() | notes.keys()
    students: dict[str, Student] = {}

    for email in all_emails:
        all_dates = (
            enrollments.get(email, set())
            | results.get(email, {}).keys()
            | notes.get(email, {}).keys()
        )
        events = []
        for date in sorted(all_dates, reverse=True):
            events.append(ExamEvent(
                date=date,
                risultato=results.get(email, {}).get(date, 'AS'),
                note=notes.get(email, {}).get(date),
            ))
        students[email] = Student(
            email=email,
            matricola=email2mat.get(email, ''),
            name=names.get(email, ''),
            events=events,
        )

    return students
