# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import logging
import os
from pathlib import Path

import click

from examui import config
from examui.pipeline import db


def _exam_date() -> str:
  files = sorted((config.HISTORY_DIR / 'iscrizioni').glob('*.xls'))
  if not files:
    raise click.ClickException(f'No iscrizioni XLS files in {config.HISTORY_DIR}/iscrizioni')
  return files[-1].stem


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable debug logging')
@click.pass_context
def cli(ctx, verbose):
  """Exam data pipeline for examui."""
  logging.basicConfig(
    level=logging.DEBUG if verbose else logging.INFO,
    format='%(levelname)s %(name)s %(message)s',
  )

  pipeline = config.PIPELINE
  if not pipeline:
    raise click.ClickException('Missing [pipeline] section in config.toml')

  ctx.ensure_object(dict)
  ctx.obj['work_dir'] = Path(pipeline['work_dir'])
  ctx.obj['db_path'] = Path(pipeline['work_dir']) / 'pipeline.db'
  ctx.obj['exam_date'] = _exam_date()


@cli.command('fetch-uploads')
@click.pass_context
def fetch_uploads_cmd(ctx):
  """Download student submissions from the uploads API."""
  from examui.pipeline.fetch import fetch_uploads

  password = os.environ.get('UPLOADS_PASSWORD')
  if not password:
    raise click.ClickException('UPLOADS_PASSWORD env var not set')

  with db.connect(ctx.obj['db_path']) as conn:
    count = fetch_uploads(conn, config.PIPELINE.get('uploads', {}), password, ctx.obj['work_dir'])
  click.echo(f'Fetched {count} uploads')


@cli.command('fetch-calendar')
@click.pass_context
def fetch_calendar_cmd(ctx):
  """Download calendar bookings from cal.com."""
  from examui.pipeline.fetch import fetch_calendar

  calcom_key = os.environ.get('CALCOM_KEY')
  if not calcom_key:
    raise click.ClickException('CALCOM_KEY env var not set')

  with db.connect(ctx.obj['db_path']) as conn:
    history_emails = [r['email'] for r in db.all_history(conn)]
    if not history_emails:
      from examui.data.history import enrolled_emails
      history_emails = list(enrolled_emails(config.HISTORY_DIR, ctx.obj['exam_date']))

    count = fetch_calendar(
      conn, config.PIPELINE.get('calendar', {}), calcom_key,
      ctx.obj['exam_date'], history_emails,
    )
  click.echo(f'Fetched {count} calendar bookings')


@cli.command('load-history')
@click.pass_context
def load_history_cmd(ctx):
  """Load enrollment and exam history from XLS files."""
  from examui.pipeline.collect import load_history

  with db.connect(ctx.obj['db_path']) as conn:
    count = load_history(conn, ctx.obj['exam_date'], config.HISTORY_DIR, config.COURSE_NAME)
  click.echo(f'Loaded history for {count} students')


@cli.command()
@click.option('--student', '-s', default=None, help='Process a single student (email username)')
@click.option('--force', '-f', is_flag=True, help='Recompute even if source unchanged')
@click.option('--workers', '-w', default=None, type=int, help='Parallel workers (default: auto)')
@click.pass_context
def compute(ctx, student, force, workers):
  """Run gradle tests, javadoc, and pygount for each student."""
  from examui.pipeline.compute import compute_all

  if workers is None:
    workers = min(os.cpu_count() or 4, 8)

  with db.connect(ctx.obj['db_path']) as conn:
    done, skipped, errors = compute_all(
      conn,
      work_dir=ctx.obj['work_dir'],
      student_base=config.STUDENT_BASE,
      projects_dir=config.PROJECTS_DIR,
      exam_date=ctx.obj['exam_date'],
      force=force,
      workers=workers,
      student_filter=student,
    )
  click.echo(f'Done: {done} computed, {skipped} skipped, {errors} errors')


@cli.command()
@click.pass_context
def collect(ctx):
  """Assemble marks.tsv from DB data and history."""
  from examui.pipeline.collect import collect_marks, noshow_emails

  with db.connect(ctx.obj['db_path']) as conn:
    path = collect_marks(conn, ctx.obj['exam_date'], config.EVALS_DIR)
    noshow = noshow_emails(conn)

  click.echo(f'Wrote {path}')
  if noshow:
    click.echo(f'No-shows ({len(noshow)}):')
    for email in noshow:
      click.echo(f'  {email}')


@cli.command()
@click.option('--workers', '-w', default=None, type=int, help='Parallel workers (default: auto)')
@click.pass_context
def run(ctx, workers):
  """Run the full pipeline: load-history + fetch + compute + collect."""
  ctx.invoke(load_history_cmd)
  ctx.invoke(fetch_uploads_cmd)
  ctx.invoke(fetch_calendar_cmd)
  ctx.invoke(compute, workers=workers)
  ctx.invoke(collect)


@cli.command()
@click.pass_context
def status(ctx):
  """Show pipeline status summary."""
  with db.connect(ctx.obj['db_path']) as conn:
    uploads = len(db.all_uploads(conn))
    calendar = len(db.all_calendar(conn))
    history = len(db.all_history(conn))
    computed = len(db.all_computed(conn))

  click.echo(f'Exam date:  {ctx.obj["exam_date"]}')
  click.echo(f'Uploads:    {uploads}')
  click.echo(f'Calendar:   {calendar}')
  click.echo(f'History:    {history}')
  click.echo(f'Computed:   {computed}')
