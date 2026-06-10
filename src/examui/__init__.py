# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from flask import Flask, redirect, url_for


def create_app():
    app = Flask(__name__)

    from examui.views.oral import bp as oral_bp
    from examui.views.history import bp as history_bp

    app.register_blueprint(oral_bp)
    app.register_blueprint(history_bp)

    @app.get('/')
    def index():
        return redirect(url_for('history.list_students'))

    return app
