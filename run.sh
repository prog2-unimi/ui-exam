#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini
set -e

# Environment variables are expected from .envrc (direnv) or the calling shell.

echo "EXAM_DATE:    $EXAM_DATE"
echo "HISTORY_DIR:  $HISTORY_DIR"
echo "EVALS_DIR:    $EVALS_DIR"
echo "STUDENT_BASE: $STUDENT_BASE"

export FLASK_APP=examui
export FLASK_DEBUG="${FLASK_DEBUG:-1}"

cd "$(dirname "$0")"
exec uv run flask run --host 127.0.0.1 --port 8765 "$@"
