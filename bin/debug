#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini
set -e

# Required: HISTORY_DIR, EVALS_DIR, STUDENT_BASE

echo "HISTORY_DIR:  $HISTORY_DIR"
echo "EVALS_DIR:    $EVALS_DIR"
echo "STUDENT_BASE: $STUDENT_BASE"

cd "$(dirname "$0")"
exec uv run gunicorn --workers=1 --reload --bind=127.0.0.1:8765 'examui:create_app()' "$@"
