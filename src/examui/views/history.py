# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import dataclasses
from datetime import datetime

from flask import Blueprint, render_template
from examui.models.store import all_students, exam_date, UnderEvaluationEvent

bp = Blueprint('history', __name__, url_prefix='')


@bp.get('/history')
def list_students():
  students = all_students()
  current_date = datetime.strptime(exam_date(), '%y%m%d').date().isoformat()

  summary = []
  all_dates = set()

  for s in sorted(students.values(), key=lambda s: s.name):
    event_dates = sorted({e.date.isoformat() for e in s.events}, reverse=True)
    all_dates.update(d for d in event_dates if d != current_date)

    in_current = bool(s.events) and isinstance(s.events[0], UnderEvaluationEvent)
    sm = s.summary_mark

    summary.append(
      {
        'email': s.email,
        'name': s.name,
        'matricola': s.matricola,
        'attempts': s.attempts,
        'first': s.first.isoformat() if s.first else None,
        'last': s.last.isoformat() if s.last else None,
        'first_attempt': s.first_attempt.isoformat() if s.first_attempt else None,
        'in_current': in_current,
        'dates': event_dates,
        'summary_mark': dataclasses.asdict(sm) if sm else None,
      }
    )

  return render_template(
    'history.html',
    students=summary,
    current_date=current_date,
    exam_dates=sorted(all_dates, reverse=True),
  )
