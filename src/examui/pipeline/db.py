# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS uploads (
    email       TEXT PRIMARY KEY,
    upload_date TEXT NOT NULL,
    upload_id   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar (
    email     TEXT PRIMARY KEY,
    slot_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    email      TEXT PRIMARY KEY,
    matricola  TEXT NOT NULL,
    num        INTEGER NOT NULL DEFAULT 0,
    first_date TEXT NOT NULL DEFAULT '',
    first_real TEXT NOT NULL DEFAULT '',
    last_date  TEXT NOT NULL DEFAULT '',
    rejected   TEXT NOT NULL DEFAULT '',
    accepted   TEXT NOT NULL DEFAULT '',
    other      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS computed (
    email          TEXT PRIMARY KEY,
    source_hash    TEXT NOT NULL,
    tests_status   TEXT NOT NULL DEFAULT '',
    javadoc_status TEXT NOT NULL DEFAULT '',
    javadoc_cyclic TEXT NOT NULL DEFAULT 'NO',
    sloc_code      INTEGER NOT NULL DEFAULT 0,
    sloc_docs      INTEGER NOT NULL DEFAULT 0,
    sloc_files     INTEGER NOT NULL DEFAULT 0,
    slocc_code     INTEGER NOT NULL DEFAULT 0,
    slocc_files    INTEGER NOT NULL DEFAULT 0
);
"""


@contextmanager
def connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
  db_path.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(db_path)
  conn.row_factory = sqlite3.Row
  conn.executescript(_SCHEMA)
  try:
    yield conn
    conn.commit()
  except BaseException:
    conn.rollback()
    raise
  finally:
    conn.close()


def clear_table(conn: sqlite3.Connection, table: str) -> None:
  conn.execute(f'DELETE FROM {table}')  # noqa: S608 — table name is internal


def upsert_upload(conn: sqlite3.Connection, email: str, upload_date: str, upload_id: int) -> None:
  conn.execute(
    'INSERT OR REPLACE INTO uploads (email, upload_date, upload_id) VALUES (?, ?, ?)',
    (email, upload_date, upload_id),
  )


def upsert_calendar(conn: sqlite3.Connection, email: str, slot_date: str) -> None:
  conn.execute(
    'INSERT OR REPLACE INTO calendar (email, slot_date) VALUES (?, ?)',
    (email, slot_date),
  )


def upsert_history(
  conn: sqlite3.Connection,
  email: str,
  matricola: str,
  num: int = 0,
  first_date: str = '',
  first_real: str = '',
  last_date: str = '',
  rejected: str = '',
  accepted: str = '',
  other: str = '',
) -> None:
  conn.execute(
    'INSERT OR REPLACE INTO history'
    ' (email, matricola, num, first_date, first_real, last_date, rejected, accepted, other)'
    ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
    (email, matricola, num, first_date, first_real, last_date, rejected, accepted, other),
  )


def upsert_computed(
  conn: sqlite3.Connection,
  email: str,
  source_hash: str,
  tests_status: str = '',
  javadoc_status: str = '',
  javadoc_cyclic: str = 'NO',
  sloc_code: int = 0,
  sloc_docs: int = 0,
  sloc_files: int = 0,
  slocc_code: int = 0,
  slocc_files: int = 0,
) -> None:
  conn.execute(
    'INSERT OR REPLACE INTO computed'
    ' (email, source_hash, tests_status, javadoc_status, javadoc_cyclic,'
    '  sloc_code, sloc_docs, sloc_files, slocc_code, slocc_files)'
    ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    (
      email, source_hash, tests_status, javadoc_status, javadoc_cyclic,
      sloc_code, sloc_docs, sloc_files, slocc_code, slocc_files,
    ),
  )


def get_computed_hash(conn: sqlite3.Connection, email: str) -> str | None:
  row = conn.execute('SELECT source_hash FROM computed WHERE email = ?', (email,)).fetchone()
  return row['source_hash'] if row else None


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
  return [dict(r) for r in conn.execute(f'SELECT * FROM {table}').fetchall()]  # noqa: S608


def all_uploads(conn: sqlite3.Connection) -> list[dict]:
  return _rows(conn, 'uploads')


def all_calendar(conn: sqlite3.Connection) -> list[dict]:
  return _rows(conn, 'calendar')


def all_history(conn: sqlite3.Connection) -> list[dict]:
  return _rows(conn, 'history')


def all_computed(conn: sqlite3.Connection) -> list[dict]:
  return _rows(conn, 'computed')
