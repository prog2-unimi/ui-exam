# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

_LEADING_COMMENT_RE = re.compile(r'\A\s*/\*.*?\*/\s*', re.DOTALL)

# package-info.java/module-info.java's leading comment is the package/module's
# own required Javadoc, not a license-header slot: spotless's licenseHeaderFile
# step never touches headers on these files (confirmed empirically — it leaves
# them alone even when no header is present at all), so stripping it here would
# just delete required Javadoc that nothing puts back, breaking `javadoc -Werror`.
_NO_HEADER_NAMES = {'package-info.java', 'module-info.java'}


def _strip_leading_comment(java_dir: Path) -> None:
  """Remove a leading block comment before spotless's licenseHeaderFile step runs.

  Spotless locates the old header by cutting the file, verbatim as text, at
  the first line starting with `package`/`import`; it has no notion of
  comment structure. If a student's leading block comment doesn't close
  before that line (e.g. it's glued straight into `package`/`import` with no
  newline, or the comment spans past it entirely — even to the point of
  wrapping the whole file), spotless's cut still lands past the comment's
  true close, so the surviving tail keeps a `*/` with no matching opener,
  producing a broken file. Stripping the whole leading comment ourselves —
  correct without tracking nesting, since Java's `/* */` doesn't nest — keeps
  spotless's replacement well-behaved regardless of what a student's opening
  comment contains or where it actually ends.
  """
  for path in java_dir.rglob('*.java'):
    if path.name in _NO_HEADER_NAMES:
      continue
    text = path.read_text()
    stripped = _LEADING_COMMENT_RE.sub('', text, count=1)
    if stripped != text:
      path.write_text(stripped)


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
  _strip_leading_comment(java_dir)

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
