# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import logging

from flask import Flask, redirect, url_for

_log = logging.getLogger(__name__)


def _configure_logging() -> None:
  gunicorn = logging.getLogger("gunicorn.error")
  if gunicorn.handlers:
    logging.root.handlers = gunicorn.handlers
    logging.root.setLevel(gunicorn.level or logging.INFO)
  else:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def create_app():
  _configure_logging()
  app = Flask(__name__)

  from examui.views.student import bp as student_bp
  from examui.views.history import bp as history_bp
  from examui.views.schedule import bp as schedule_bp

  app.register_blueprint(student_bp)
  app.register_blueprint(history_bp)
  app.register_blueprint(schedule_bp)

  @app.get("/")
  def index():
    return redirect(url_for("history.list_students"))

  from pathlib import Path
  from examui.models.store import all_students, UnderEvaluationEvent
  from examui.models import source

  Path(app.static_folder, "pygments.css").write_text(source.pygments_css())
  students = all_students()
  with_source = sorted(
    e for e, s in students.items() if s.events and isinstance(s.events[0], UnderEvaluationEvent)
  )
  _log.info("[warmup] %d students with source", len(with_source))
  for email in with_source:
    source.warmup(email)
  _log.info("[warmup] complete")

  return app
