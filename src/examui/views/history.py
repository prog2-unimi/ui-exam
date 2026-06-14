# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import dataclasses

from flask import Blueprint, render_template
from examui.models.store import all_students, exam_date

bp = Blueprint('history', __name__, url_prefix='')


@bp.get('/history')
def list_students():
    students     = all_students()
    current_date = exam_date()

    summary   = []
    all_dates = set()

    for s in sorted(students.values(), key=lambda s: s.name):
        event_dates = sorted({e.date for e in s.events}, reverse=True)
        all_dates.update(event_dates)

        in_current = s.current is not None
        sm         = s.summary_mark
        dates      = event_dates + ([current_date] if in_current else [])

        summary.append({
            'email':         s.email,
            'name':          s.name,
            'matricola':     s.matricola,
            'attempts':      s.attempts,
            'first':         s.first,
            'last':          s.last,
            'first_attempt': s.first_attempt,
            'in_current':    in_current,
            'dates':         dates,
            'summary_mark':  dataclasses.asdict(sm) if sm else None,
        })

    return render_template('history.html',
                           students=summary,
                           current_date=current_date,
                           exam_dates=sorted(all_dates, reverse=True))
