# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import json

from flask import Blueprint, render_template
from examui.models.history import all_students
from examui.models import oral
from examui import config

bp = Blueprint('history', __name__, url_prefix='/history')


@bp.get('/')
def list_students():
    students = all_students()
    summary = []
    all_dates = set()
    for s in sorted(students.values(), key=lambda s: s.name):
        dates = sorted({e.date for e in s.events}, reverse=True)
        all_dates.update(dates)
        first_eval = next((e.date for e in reversed(s.events) if e.risultato != 'AS'), '')
        has_refused = any(
            e.risultato[-1:] == 'R' and e.risultato[:2] not in ('RI', 'RE')
            for e in s.events
        )
        summary.append({
            'email':       s.email,
            'name':        s.name,
            'matricola':   s.matricola,
            'n':           sum(1 for e in s.events if e.risultato != 'AS'),
            'first':       dates[-1] if dates else '',
            'last':        dates[0]  if dates else '',
            'first_eval':  first_eval,
            'has_refused': has_refused,
            'has_source':  oral.has_source(s.email),
            'dates':       dates,
        })
    return render_template('list.html',
                           students_json=json.dumps(summary),
                           exam_dates=sorted(all_dates, reverse=True),
                           exam_date=config.EXAM_DATE)


@bp.get('/<email>')
def detail(email):
    students = all_students()
    student  = students.get(email)
    if student is None:
        return 'Student not found', 404
    return render_template('detail.html',
                           student=student,
                           exam_date=config.EXAM_DATE)
