# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import json

from flask import Blueprint, render_template
from examui.models.history import all_students, exam_date

bp = Blueprint('history', __name__, url_prefix='')



@bp.get('/')
def list_students():
    current_date = exam_date()
    students     = all_students()

    summary   = []
    all_dates = set()

    for s in sorted(students.values(), key=lambda s: s.name):
        event_dates = sorted({e.date for e in s.events}, reverse=True)
        dates       = ([current_date] + event_dates) if s.current else event_dates
        all_dates.update(dates)

        first_eval  = next((e.date for e in reversed(s.events) if e.mark != 'AS'), '')
        has_refused = any(
            e.mark[-1:] == 'R' and e.mark[:2] not in ('RI', 'RE')
            for e in s.events
        )

        current_mark = s.current.mark if s.current else None

        summary.append({
            'email':        s.email,
            'name':         s.name,
            'matricola':    s.matricola,
            'n':            sum(1 for e in s.events if e.mark != 'AS'),
            'first':        dates[-1] if dates else '',
            'last':         dates[0]  if dates else '',
            'first_eval':   first_eval,
            'has_refused':  has_refused,
            'has_source':   current_mark is not None and current_mark != 'AS',
            'dates':        dates,
            'verbali_mark': s.verbali_mark,
            'current_mark': current_mark,
        })

    return render_template('list.html',
                           students_json=json.dumps(summary),
                           exam_dates=sorted(all_dates, reverse=True),
                           exam_date=current_date)
