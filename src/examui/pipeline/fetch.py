# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import requests
from rapidfuzz import process

from examui.pipeline import db

_log = logging.getLogger(__name__)


def _date_l2s(utc: str) -> str:
  return (
    datetime.strptime(utc, '%Y-%m-%dT%H:%M:%S.%fZ')
    .replace(tzinfo=timezone.utc)
    .astimezone(tz=None)
    .strftime('%y%m%d-%H%M')
  )


def _date_s2l(short: str) -> str:
  return (
    datetime.strptime(short, '%y%m%d')
    .replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    .strftime('%Y-%m-%dT%H:%M:%S.000Z')
  )


def fetch_uploads(
  conn: sqlite3.Connection,
  conf: dict,
  password: str,
  work_dir: Path,
) -> int:
  url = conf['url']
  resp = requests.post(f'{url}/login', json={'username': conf['username'], 'password': password})
  resp.raise_for_status()
  jwt = resp.json()['jwt']
  headers = {'authorization': f'Bearer {jwt}'}

  session = requests.get(f'{url}/session/{conf["session"]}', headers=headers)
  session.raise_for_status()
  uploads = session.json()['session']['Uploads']

  latest: dict[str, dict] = {}
  for up in uploads:
    if up['FILENAME'] != 'consegna.zip':
      continue
    user = up['EMAIL']
    date = _date_l2s(up['DATE'])
    if user not in latest or date > latest[user]['date']:
      latest[user] = {'id': up['ID'], 'user': user, 'date': date}

  if not latest:
    _log.warning('No uploads found')
    zip_path = work_dir / 'uploaded.zip'
    with ZipFile(zip_path, 'w'):
      pass
    return 0

  upload_ids = [v['id'] for v in latest.values()]
  resp = requests.post(
    f'{url}/session/lastfiles/{conf["session"]}?groupby=email',
    headers=headers,
    json={'uploads': upload_ids},
  )
  if resp.status_code == 404:
    _log.warning('No uploads yet (404)')
    return 0
  resp.raise_for_status()

  zip_path = work_dir / 'uploaded.zip'
  zip_path.parent.mkdir(parents=True, exist_ok=True)
  zip_path.write_bytes(resp.content)

  uploaded_dir = work_dir / 'uploaded'
  uploaded_dir.mkdir(parents=True, exist_ok=True)
  with ZipFile(zip_path) as zf:
    zf.extractall(uploaded_dir)

  db.clear_table(conn, 'uploads')
  for info in latest.values():
    email = info['user'].split('@')[0]
    db.upsert_upload(conn, email, info['date'], info['id'])

  _log.info('Fetched %d uploads', len(latest))
  return len(latest)


def fetch_calendar(
  conn: sqlite3.Connection,
  conf: dict,
  calcom_key: str,
  exam_date: str,
  enrolled_emails: list[str],
) -> int:
  resp = requests.get(
    conf['endpoint'],
    headers={
      'Authorization': f'Bearer {calcom_key}',
      'cal-api-version': conf['version'],
      'Content-Type': 'application/json',
    },
    params={
      'eventTypeId': conf['event'],
      'status': 'upcoming,past',
      'afterStart': _date_s2l(exam_date),
      'take': 200,
    },
  )
  resp.raise_for_status()
  appointments = resp.json()['data']

  raw: list[tuple[str, str]] = []
  for appt in appointments:
    if appt['status'].upper() != 'ACCEPTED':
      continue
    when = _date_l2s(appt['start'])
    if when < exam_date:
      continue
    email = appt['attendees'][0]['email'].split('@')[0].lower()
    raw.append((email, when))

  if not enrolled_emails:
    _log.warning('No enrolled emails for fuzzy matching — storing raw calendar emails')
    choices = []
  else:
    choices = list(enrolled_emails)

  cleaned: dict[str, str] = {}
  for query, when in raw:
    if choices:
      result, score, _ = process.extractOne(query, choices)
      if score < 50:
        _log.warning('Calendar email %s has no good match (best: %s, score: %d) — skipping', query, result, score)
        continue
      if score < 100:
        print(f'Mapped {query} to {result} (score {score})', flush=True, file=sys.stderr)
      matched = result
    else:
      matched = query
    if matched not in cleaned or when > cleaned[matched]:
      cleaned[matched] = when

  db.clear_table(conn, 'calendar')
  for email, slot in cleaned.items():
    db.upsert_calendar(conn, email, slot)

  _log.info('Fetched %d calendar bookings', len(cleaned))
  return len(cleaned)
