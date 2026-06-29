# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from rich.progress import (
  BarColumn,
  MofNCompleteColumn,
  Progress,
  SpinnerColumn,
  TextColumn,
  TimeElapsedColumn,
)

_log = logging.getLogger(__name__)

_RESULTS_RE = re.compile(
  r'.+^Results: (?P<Status>\w+) '
  r'\((?P<Tests>\d+) tests, (?P<Successes>\d+) successes, '
  r'(?P<Failures>\d+) failures, (?P<Skipped>\d+) skipped\)$',
  re.DOTALL | re.MULTILINE,
)
_JAVADOC_ERRORS_RE = re.compile(r'.+^(?P<errors>\d+) errors?', re.MULTILINE | re.DOTALL)
_JAVADOC_WARNINGS_RE = re.compile(r'.+^(?P<warnings>\d+) warnings?', re.MULTILINE | re.DOTALL)
_JAVADOC_CYCLIC_RE = re.compile(
  r'.+^warning: .+ cyclic package dependencies detected', re.MULTILINE | re.DOTALL
)


def _hash_file(path: Path) -> str:
  return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_source(
  email: str, consegna: Path, template_zip: Path, student_base: Path
) -> Path:
  source_dir = student_base / email / 'source'
  if source_dir.exists():
    shutil.rmtree(source_dir)
  source_dir.mkdir(parents=True)

  with ZipFile(template_zip) as zf:
    zf.extractall(source_dir)

  subdirs = list(source_dir.iterdir())
  if len(subdirs) == 1 and subdirs[0].is_dir():
    top = subdirs[0]
    for item in top.iterdir():
      item.rename(source_dir / item.name)
    top.rmdir()

  java_dir = source_dir / 'src' / 'main' / 'java'
  if java_dir.exists():
    shutil.rmtree(java_dir)
  java_dir.mkdir(parents=True)

  with ZipFile(consegna) as zf:
    zf.extractall(java_dir)

  for d in source_dir.rglob('*'):
    if d.is_dir():
      d.chmod(0o700)
  for f in source_dir.rglob('*'):
    if f.is_file():
      f.chmod(0o600)
  gradlew = source_dir / 'gradlew'
  if gradlew.exists():
    gradlew.chmod(0o700)

  header = source_dir / 'src' / 'licenseHeaderFile.txt'
  header.write_text(f'/* {email} */\n\n')

  subprocess.run(
    ['./gradlew', '--no-build-cache', 'spotlessApply'],
    cwd=source_dir,
    capture_output=True,
    timeout=120,
  )

  return source_dir


def _run_tests(source_dir: Path, computed_dir: Path) -> str:
  try:
    result = subprocess.run(
      ['./gradlew', '--no-build-cache', 'clean', 'test'],
      cwd=source_dir,
      capture_output=True,
      text=True,
      timeout=300,
    )
    stdout = result.stdout
  except subprocess.TimeoutExpired:
    _log.warning('Tests timed out')
    stdout = 'TIMEOUT'

  (computed_dir / 'tests.stdout').write_text(stdout)

  m = _RESULTS_RE.match(stdout)
  if m:
    return m.group('Status')
  return 'FAILURE'


def _run_javadoc(source_dir: Path, computed_dir: Path, javadoc_dir: Path) -> tuple[str, str]:
  try:
    result = subprocess.run(
      ['./gradlew', '--no-build-cache', 'clean', 'javadoc'],
      cwd=source_dir,
      capture_output=True,
      text=True,
      timeout=300,
    )
    output = result.stdout + '\n' + result.stderr
  except subprocess.TimeoutExpired:
    _log.warning('Javadoc timed out')
    output = 'TIMEOUT'

  (computed_dir / 'javadoc.stdout').write_text(output)

  build_javadoc = source_dir / 'build' / 'docs' / 'javadoc'
  if javadoc_dir.exists():
    shutil.rmtree(javadoc_dir)
  if build_javadoc.exists():
    shutil.copytree(build_javadoc, javadoc_dir)
  else:
    javadoc_dir.mkdir(parents=True, exist_ok=True)

  status = 'SUCCESS' if 'BUILD SUCCESSFUL' in output else 'FAILURE'
  cyclic = 'YES' if _JAVADOC_CYCLIC_RE.match(output) else 'NO'
  return status, cyclic


def _run_pygount(source_dir: Path, trivial_packages: frozenset[str]) -> dict:
  java_dir = source_dir / 'src' / 'main' / 'java'
  metrics = {
    'sloc_code': 0, 'sloc_docs': 0, 'sloc_files': 0,
    'slocc_code': 0, 'slocc_files': 0,
  }

  skip = ','.join(sorted(trivial_packages))
  try:
    result = subprocess.run(
      ['pygount', '-F', skip, '-f', 'json', str(java_dir)],
      capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
      summary = json.loads(result.stdout).get('summary', {})
      metrics['sloc_code'] = summary.get('totalCodeCount', 0)
      metrics['sloc_docs'] = summary.get('totalDocumentationCount', 0)
      metrics['sloc_files'] = summary.get('totalFileCount', 0)
  except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
    _log.warning('pygount (main) failed: %s', e)

  for pkg in sorted(trivial_packages):
    pkg_dir = java_dir / pkg
    if not pkg_dir.exists():
      continue
    try:
      result = subprocess.run(
        ['pygount', '-f', 'json', str(pkg_dir)],
        capture_output=True, text=True, timeout=60,
      )
      if result.returncode == 0:
        summary = json.loads(result.stdout).get('summary', {})
        metrics['slocc_code'] += summary.get('totalCodeCount', 0)
        metrics['slocc_files'] += summary.get('totalFileCount', 0)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
      _log.warning('pygount (%s) failed: %s', pkg, e)

  return metrics


def _compute_one(
  email: str,
  student_base: Path,
  work_dir: Path,
  template_zip: Path,
  existing_hashes: dict[str, str],
  force: bool,
  trivial_packages: frozenset[str],
  progress: Progress | None = None,
) -> tuple[str, dict | None]:
  """Compute metrics for one student. Returns (email, metrics_dict_or_None)."""
  consegna = None
  uploaded_dir = work_dir / 'uploaded'
  for d in uploaded_dir.glob(f'{email}@*/consegna.zip'):
    consegna = d
    break

  if consegna is None:
    return email, None

  try:
    current_hash = _hash_file(consegna)
  except OSError as e:
    _log.error('Cannot read %s: %s', consegna, e)
    return email, None

  if not force and existing_hashes.get(email) == current_hash:
    return email, None

  task = progress.add_task(email, total=4, status='extracting') if progress else None
  try:
    try:
      source_dir = _extract_source(email, consegna, template_zip, student_base)
    except (BadZipFile, OSError) as e:
      _log.error('Source extraction failed for %s: %s', email, e)
      return email, None

    computed_dir = student_base / email / 'computed'
    computed_dir.mkdir(parents=True, exist_ok=True)
    javadoc_dir = student_base / email / 'javadoc'

    if progress:
      progress.update(task, status='testing', advance=1)
    tests_status = _run_tests(source_dir, computed_dir)

    if progress:
      progress.update(task, status='javadoc', advance=1)
    javadoc_status, javadoc_cyclic = _run_javadoc(source_dir, computed_dir, javadoc_dir)

    if progress:
      progress.update(task, status='pygount', advance=1)
    sloc = _run_pygount(source_dir, trivial_packages)

    if progress:
      progress.advance(task)

    (computed_dir / 'source.hash').write_text(current_hash)

    return email, {
      'source_hash': current_hash,
      'tests_status': tests_status,
      'javadoc_status': javadoc_status,
      'javadoc_cyclic': javadoc_cyclic,
      **sloc,
    }
  finally:
    if task is not None:
      progress.remove_task(task)


def compute_all(
  conn,
  work_dir: Path,
  student_base: Path,
  projects_dir: Path,
  exam_date: str,
  trivial_packages: frozenset[str],
  force: bool = False,
  workers: int | None = None,
  student_filter: str | None = None,
) -> tuple[int, int, int]:
  """Returns (computed_count, skipped_count, error_count)."""
  template_zip = projects_dir / f'{exam_date}.zip'
  if not template_zip.exists():
    raise FileNotFoundError(f'Template zip not found: {template_zip}')

  uploaded_dir = work_dir / 'uploaded'
  if not uploaded_dir.exists():
    raise FileNotFoundError(f'No uploaded directory: {uploaded_dir}')

  students = set()
  for d in uploaded_dir.glob('*@*/consegna.zip'):
    students.add(d.parent.name.split('@')[0])

  if student_filter:
    if student_filter not in students:
      raise ValueError(f'Student {student_filter} not found in uploads')
    students = {student_filter}

  existing_hashes: dict[str, str] = {}
  for row in conn.execute('SELECT email, source_hash FROM computed').fetchall():
    existing_hashes[row['email']] = row['source_hash']

  computed_count = 0
  skipped_count = 0
  error_count = 0
  total = len(students)

  from examui.pipeline.db import upsert_computed

  progress = Progress(
    SpinnerColumn(),
    TextColumn('[progress.description]{task.description}'),
    BarColumn(),
    MofNCompleteColumn(),
    TextColumn('[dim]{task.fields[status]}[/dim]'),
    TimeElapsedColumn(),
  )

  with progress:
    task = progress.add_task('Computing', total=total, status='')

    with ThreadPoolExecutor(max_workers=workers) as pool:
      futures = {
        pool.submit(
          _compute_one, email, student_base, work_dir, template_zip,
          existing_hashes, force, trivial_packages, progress,
        ): email
        for email in sorted(students)
      }
      for future in as_completed(futures):
        email = futures[future]
        try:
          _, metrics = future.result()
        except Exception:
          _log.exception('Unexpected error computing %s', email)
          error_count += 1
          progress.console.print(f'  [red]✗[/red] {email} — ERROR')
          progress.advance(task)
          continue

        if metrics is None:
          skipped_count += 1
          progress.console.print(f'  [dim]- {email} — skipped[/dim]')
        else:
          upsert_computed(conn, email, **metrics)
          conn.commit()
          computed_count += 1
          ts = '[green]OK[/green]' if metrics['tests_status'] == 'SUCCESS' else '[red]FAIL[/red]'
          js = '[green]OK[/green]' if metrics['javadoc_status'] == 'SUCCESS' else '[red]FAIL[/red]'
          progress.console.print(f'  {email} — tests: {ts}  javadoc: {js}')

        progress.advance(task)

  return computed_count, skipped_count, error_count
