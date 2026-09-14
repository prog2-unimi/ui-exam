# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from examui.data.extraction import _strip_leading_comment


def test_strips_glued_leading_comment_before_package(tmp_path):
  f = tmp_path / 'A.java'
  f.write_text('/* header */package foo;\n\nclass A {}\n')
  _strip_leading_comment(tmp_path)
  assert f.read_text() == 'package foo;\n\nclass A {}\n'


def test_strips_glued_leading_comment_before_import(tmp_path):
  f = tmp_path / 'A.java'
  f.write_text('/* header */import java.util.List;\n\nclass A {}\n')
  _strip_leading_comment(tmp_path)
  assert f.read_text() == 'import java.util.List;\n\nclass A {}\n'


def test_strips_well_formed_leading_comment(tmp_path):
  f = tmp_path / 'A.java'
  f.write_text('/* header */\npackage foo;\n\nclass A {}\n')
  _strip_leading_comment(tmp_path)
  assert f.read_text() == 'package foo;\n\nclass A {}\n'


def test_leaves_files_without_leading_comment_untouched(tmp_path):
  f = tmp_path / 'A.java'
  original = 'package foo;\n\nclass A {}\n'
  f.write_text(original)
  _strip_leading_comment(tmp_path)
  assert f.read_text() == original


def test_recurses_into_subdirectories(tmp_path):
  sub = tmp_path / 'pkg'
  sub.mkdir()
  f = sub / 'B.java'
  f.write_text('/* header */package pkg;\n')
  _strip_leading_comment(tmp_path)
  assert f.read_text() == 'package pkg;\n'


def test_strips_comment_spanning_past_the_delimiter(tmp_path):
  """Regression test: a leading comment that doesn't close before the first
  package/import line used to leave its `*/` orphaned once spotless cut the
  file there, breaking compilation (see davide.ciaramidaro, 61514A, exam
  2026-09-11: their whole Main.java was wrapped in one unclosed comment)."""
  f = tmp_path / 'Main.java'
  f.write_text(
    '/*package codice;\n'
    '\n'
    'import java.util.Scanner;\n'
    '\n'
    'public class Main {\n'
    '    public static void main(String[] args) {}\n'
    '}\n'
    '*/\n'
  )
  _strip_leading_comment(tmp_path)
  assert f.read_text() == ''


def test_leaves_package_info_javadoc_untouched(tmp_path):
  """Regression test: package-info.java's leading comment is the package's
  own required Javadoc, not a discardable license header. Spotless never
  replaces headers on this file, so stripping it here deletes required
  Javadoc that nothing puts back, failing `javadoc -Werror` with "no
  comment" (see tommaso.bromuri, 41286A, exam 2026-09-11)."""
  f = tmp_path / 'package-info.java'
  original = '/**\n * Package docs.\n */\npackage foo;\n'
  f.write_text(original)
  _strip_leading_comment(tmp_path)
  assert f.read_text() == original


def test_leaves_module_info_untouched(tmp_path):
  f = tmp_path / 'module-info.java'
  original = '/** Module docs. */\nmodule foo {}\n'
  f.write_text(original)
  _strip_leading_comment(tmp_path)
  assert f.read_text() == original
