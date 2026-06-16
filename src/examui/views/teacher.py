# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from flask import Blueprint, abort, render_template

from examui.models.store import load_project_htmls

bp = Blueprint('teacher', __name__, url_prefix='')


@bp.get('/teacher')
def teacher():
  return render_template('teacher.html', files=load_project_htmls())


@bp.get('/api/teacher/file/<filename>')
def teacher_file(filename: str):
  content = next((c for n, c in load_project_htmls() if n == filename), None)
  if content is None:
    abort(404)
  return content, 200, {'Content-Type': 'text/html; charset=utf-8'}
