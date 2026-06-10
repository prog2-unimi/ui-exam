# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from flask import Blueprint, Response, render_template, request, jsonify, send_from_directory
from examui.models import oral
from examui.models.history import all_students

bp = Blueprint('oral', __name__, url_prefix='/oral')


@bp.get('/<email>')
def student(email):
    df      = oral.load_marks()
    match   = df[df['email'] == email]
    row     = match.iloc[0].to_dict() if not match.empty else {}
    student = all_students().get(email)
    return render_template('oral/student.html',
                           email=email,
                           name=student.name if student else '',
                           matricola=student.matricola if student else '',
                           row=row,
                           note=oral.read_note(email),
                           has_javadoc=oral.has_javadoc(email),
                           has_source=oral.has_source(email))


@bp.post('/<email>/note')
def save_note(email):
    oral.save_note(email, request.form['note'])
    return jsonify(ok=True)


@bp.get('/<email>/javadoc/')
@bp.get('/<email>/javadoc/<path:filepath>')
def javadoc(email, filepath='index.html'):
    root = oral.javadoc_root(email)
    if not root.exists():
        return 'Javadoc not found', 404
    return send_from_directory(root, filepath)


@bp.get('/<email>/source/tree')
def source_tree(email):
    return jsonify(oral.source_tree(email))


@bp.get('/<email>/source/deps')
def source_deps(email):
    return jsonify(oral.source_deps(email))


@bp.get('/<email>/source/symbols')
def source_symbols(email):
    return jsonify(oral.source_all_symbols(email))


@bp.get('/<email>/source/file')
def source_file(email):
    relpath = request.args.get('path', '')
    data = oral.source_file(email, relpath)
    if data is None:
        return 'Not found', 404
    return jsonify(data)


@bp.get('/pygments.css')
def pygments_css():
    return Response(oral.pygments_css(), mimetype='text/css')
