# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from datetime import datetime, timedelta

from flask import Blueprint, abort, render_template, request, jsonify, send_from_directory
from examui import config
from examui.models import source
from examui.models.events import ExamEvent
from examui.models.store import all_students, UnderEvaluationEvent

bp = Blueprint('student', __name__, url_prefix='')


def _live(email: str) -> UnderEvaluationEvent | None:
  s = all_students().get(email)
  if s and s.events and isinstance(s.events[0], UnderEvaluationEvent):
    return s.events[0]
  return None


@bp.get('/student/<email>')
def student(email):
  s = all_students().get(email)
  live = _live(email)
  return render_template(
    'student.html',
    email=email,
    name=s.name if s else '',
    matricola=s.matricola if s else '',
    events=[e for e in (s.events if s else []) if isinstance(e, ExamEvent)],
    current=live,
    slot_minutes=config.SLOT_MINUTES,
  )


@bp.post('/api/<email>/note')
def save_note(email):
  live = _live(email)
  if not live:
    return jsonify(ok=False, error='not enrolled'), 404
  live.mark.note = request.form.get('note', '')
  return jsonify(ok=True)


@bp.post('/api/<email>/mark')
def save_mark(email):
  live = _live(email)
  if not live:
    return jsonify(ok=False, error='not enrolled'), 404
  live.mark.save(request.form.get('mark', ''), request.form.get('annotation', ''))
  return jsonify(ok=True)


@bp.get('/student/<email>/giustifica')
def giustifica(email):
  titolo = request.args.get('titolo', '')
  if not titolo:
    abort(400)
  students = all_students()
  if email not in students:
    matches = [e for e in students if email in e]
    if len(matches) == 1:
      email = matches[0]
    elif matches:
      return jsonify(error='ambiguous', matches=sorted(matches)), 400
    else:
      abort(404)
  live = _live(email)
  if not live:
    abort(404)
  s = all_students()[email]
  slot = live.metrics.slot
  end_slot = slot + timedelta(minutes=config.SLOT_MINUTES) if slot else None
  return render_template(
    'giustifica.html',
    titolo=titolo,
    nome=s.name,
    matricola=s.matricola,
    insegnamento=config.COURSE_NAME,
    cds=config.COURSE_DEGREE,
    data=datetime.strptime(config.TODAY, '%y%m%d').strftime('%d/%m/%Y'),
    inizio=request.args.get('inizio') or (slot.strftime('%H:%M') if slot else ''),
    fine=request.args.get('fine') or (end_slot.strftime('%H:%M') if end_slot else ''),
    presidente=config.TEACHER_NAME,
  )


@bp.get('/api/<email>/javadoc/')
@bp.get('/api/<email>/javadoc/<path:filepath>')
def javadoc(email, filepath='index.html'):
  root = source.javadoc_root(email)
  if not root.exists():
    return 'Javadoc not found', 404
  return send_from_directory(root, filepath)


@bp.get('/api/<email>/source/tree')
def source_tree(email):
  return jsonify(source.tree(email))


@bp.get('/api/<email>/source/deps')
def source_deps(email):
  return jsonify(source.deps(email))


@bp.get('/api/<email>/source/symbols')
def source_symbols(email):
  return jsonify(source.all_symbols(email))


@bp.get('/api/<email>/source/file')
def source_file(email):
  relpath = request.args.get('path', '')
  data = source.file(email, relpath)
  if data is None:
    return 'Not found', 404
  return jsonify(data)
