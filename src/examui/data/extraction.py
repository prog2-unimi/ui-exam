# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

_HEADER_GLUE_RE = re.compile(r'(\*/)(package |import )')


def _unglue_headers(java_dir: Path) -> None:
  """Insert a newline where a leading block comment runs into package/import with none.

  Spotless's licenseHeaderFile step only recognizes `package`/`import` as the
  end of the header when it starts its own line; without the newline it gets
  swallowed along with the old header, silently deleting the package
  declaration.
  """
  for path in java_dir.rglob('*.java'):
    text = path.read_text()
    fixed = _HEADER_GLUE_RE.sub(r'\1\n\2', text)
    if fixed != text:
      path.write_text(fixed)


def extract_source(
  email: str, consegna: Path, template_zip: Path, source_dir: Path
) -> Path:
  """Overlay a student's consegna.zip onto a template project and spotlessApply it.

  Shared by the pipeline's `compute` step (current exam) and the `diff` tool
  (archived past sessions) — both need the same template-overlay-and-format
  logic, just with different destination directories.
  """
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
  _unglue_headers(java_dir)

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
