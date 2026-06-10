# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import json

from flask import Blueprint, render_template
from examui.models.history import all_students

bp = Blueprint('history', __name__, url_prefix='')


@bp.get('/history')
def list_students():
    students = all_students()

    summary   = []
    all_dates = set()

    for s in sorted(students.values(), key=lambda s: s.name):
        event_dates = sorted({e.date for e in s.events}, reverse=True)
        all_dates.update(event_dates)

        first_eval  = next((e.date for e in reversed(s.events) if e.mark != 'AS'), '')
        has_refused = any(
            e.mark[-1:] == 'R' and e.mark[:2] not in ('RI', 'RE')
            for e in s.events
        )

        summary.append({
            'email':        s.email,
            'name':         s.name,
            'matricola':    s.matricola,
            'n':            sum(1 for e in s.events if e.mark != 'AS'),
            'first':        event_dates[-1] if event_dates else '',
            'last':         event_dates[0]  if event_dates else '',
            'first_eval':   first_eval,
            'has_refused':  has_refused,
            'dates':        event_dates,
            'verbali_mark': s.verbali_mark,
        })

    return render_template('history.html',
                           students_json=json.dumps(summary),
                           exam_dates=sorted(all_dates, reverse=True))
