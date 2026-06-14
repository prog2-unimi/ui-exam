# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from examui.models.store import LiveCurrentExamEvent


@dataclass(frozen=True)
class Mark:
    kind:  Literal['assente', 'respinto', 'ritirato', 'passato', 'rifiutato']
    value: int | None = None

    @classmethod
    def from_verbale(cls, voto: str, stato: str) -> Mark:
        voto2  = str(voto)[:2].upper()
        stato1 = str(stato)[:1].upper()
        if voto2 == 'RE':
            return cls(kind='respinto')
        if voto2 == 'RI':
            return cls(kind='ritirato')
        try:
            num = int(voto2)
        except ValueError:
            return cls(kind='assente')
        return cls(kind='passato' if stato1 == 'V' else 'rifiutato', value=num)


@dataclass(frozen=True)
class ExamEvent:
    date: str
    mark: Mark
    note: str | None


@dataclass(frozen=True)
class Metrics:
    tests_fail:   bool           # True = FAILURE
    javadoc_fail: bool           # True = FAILURE
    has_cycles:   bool           # True = cycles present
    main_sloc:    int            # source lines of code, clients excluded
    main_docs:    int            # documentation lines, clients excluded
    main_files:   int            # file count, clients excluded
    client_sloc:  int            # source lines of code, clients only
    client_files: int            # file count, clients only
    slot:         datetime | None  # booked oral slot (None if not booked)
    upload:       datetime | None  # submission timestamp

    @classmethod
    def from_row(cls, row: dict) -> Metrics:
        def _dt(val) -> datetime | None:
            s = str(val).strip()
            if not s:
                return None
            try:
                return datetime.strptime(s, '%y%m%d-%H%M')
            except ValueError:
                return None

        return cls(
            tests_fail=str(row.get('tests',   '')).strip().upper() != 'SUCCESS',
            javadoc_fail=str(row.get('javadoc', '')).strip().upper() != 'SUCCESS',
            has_cycles=str(row.get('cyclic',  '')).strip().upper() == 'YES',
            main_sloc=int(row.get('code',  0) or 0),
            main_docs=int(row.get('docs',  0) or 0),
            main_files=int(row.get('file',  0) or 0),
            client_sloc=int(row.get('ccode', 0) or 0),
            client_files=int(row.get('cfile', 0) or 0),
            slot=_dt(row.get('date',   '')),
            upload=_dt(row.get('upload', '')),
        )


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


@dataclass(frozen=True)
class Student:
    email:     str
    matricola: str
    name:      str
    events:    list[ExamEvent] = field(default_factory=list)
    current:   AbsentCurrentExamEvent | LiveCurrentExamEvent | None = None

    @property
    def attempts(self) -> int:
        return sum(1 for e in self.events if e.mark.kind != 'assente')

    @property
    def first(self) -> str:
        return self.events[-1].date if self.events else ''

    @property
    def last(self) -> str:
        return self.events[0].date if self.events else ''

    @property
    def first_attempt(self) -> str:
        return next((e.date for e in reversed(self.events) if e.mark.kind != 'assente'), '')

    @property
    def summary_mark(self) -> Mark | None:
        passing = next((e for e in self.events if e.mark.kind == 'passato'), None)
        if passing:
            return passing.mark
        rifiutato = next((e for e in self.events if e.mark.kind == 'rifiutato'), None)
        if rifiutato:
            return rifiutato.mark
        last = next((e for e in self.events if e.mark.kind in ('respinto', 'ritirato')), None)
        if last:
            return last.mark
        return None
