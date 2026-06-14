# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import dataclasses
from datetime import datetime

from flask import Blueprint, render_template
from examui.models.store import all_students, UnderEvaluationEvent

bp = Blueprint("schedule", __name__, url_prefix="")


@bp.get("/schedule")
def schedule():
  today = datetime.now().strftime("%Y-%m-%d")
  students = all_students()

  rows = []
  for s in sorted(
    (s for s in students.values() if s.events and isinstance(s.events[0], UnderEvaluationEvent)),
    key=lambda s: (s.events[0].metrics.slot or datetime.max, s.name),
  ):
    live = s.events[0]
    sm = s.summary_mark
    rows.append(
      {
        "email": s.email,
        "name": s.name,
        "matricola": s.matricola,
        "summary_mark": dataclasses.asdict(sm) if sm else None,
        "current_mark": live.mark.provisional,
        **dataclasses.asdict(live.metrics),
      }
    )

  return render_template("schedule.html", rows=rows, today=today)
