# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from flask import Blueprint, render_template, request, jsonify, send_from_directory
from examui import config
from examui.models import oral
from examui.models.history import all_students

bp = Blueprint('oral', __name__, url_prefix='')


@bp.get('/<email>')
def student(email):
    s = all_students().get(email)
    return render_template('oral.html',
                           email=email,
                           name=s.name if s else '',
                           matricola=s.matricola if s else '',
                           events=s.events if s else [],
                           current=s.current if s else None,
                           slot_minutes=config.SLOT_MINUTES)


@bp.post('/api/<email>/note')
def save_note(email):
    s = all_students().get(email)
    if not s or not s.current:
        return jsonify(ok=False, error='not enrolled'), 404
    s.current.note = request.form['note']
    return jsonify(ok=True)


@bp.get('/api/<email>/javadoc/')
@bp.get('/api/<email>/javadoc/<path:filepath>')
def javadoc(email, filepath='index.html'):
    root = oral.javadoc_root(email)
    if not root.exists():
        return 'Javadoc not found', 404
    return send_from_directory(root, filepath)


@bp.get('/api/<email>/source/tree')
def source_tree(email):
    return jsonify(oral.source_tree(email))


@bp.get('/api/<email>/source/deps')
def source_deps(email):
    return jsonify(oral.source_deps(email))


@bp.get('/api/<email>/source/symbols')
def source_symbols(email):
    return jsonify(oral.source_all_symbols(email))


@bp.get('/api/<email>/source/file')
def source_file(email):
    relpath = request.args.get('path', '')
    data = oral.source_file(email, relpath)
    if data is None:
        return 'Not found', 404
    return jsonify(data)
