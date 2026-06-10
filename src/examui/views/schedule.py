# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import json
from datetime import datetime

from flask import Blueprint, render_template
from examui.models.history import all_students, exam_date, LiveCurrentExamEvent

bp = Blueprint('schedule', __name__, url_prefix='')


@bp.get('/schedule')
def schedule():
    today    = datetime.now().strftime('%y%m%d')
    students = all_students()

    rows = []
    for s in sorted(
        (s for s in students.values() if isinstance(s.current, LiveCurrentExamEvent)),
        key=lambda s: (s.current.metrics.slot, s.name),
    ):
        m = s.current.metrics
        rows.append({
            'email':        s.email,
            'name':         s.name,
            'matricola':    s.matricola,
            'slot':         m.slot,
            'upload':       m.upload,
            'tests':        m.tests,
            'javadoc':      m.javadoc,
            'cyclic':       m.cyclic,
            'code':         m.code,
            'docs':         m.docs,
            'file':         m.file,
            'num':          m.num,
            'verbali_mark': s.verbali_mark,
            'current_mark': s.current.mark,
        })

    return render_template('schedule.html',
                           rows_json=json.dumps(rows),
                           exam_date=exam_date(),
                           today=today)
