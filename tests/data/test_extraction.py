# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from examui.data.extraction import _unglue_headers


def test_inserts_newline_before_glued_package(tmp_path):
  f = tmp_path / 'A.java'
  f.write_text('/* header */package foo;\n\nclass A {}\n')
  _unglue_headers(tmp_path)
  assert f.read_text() == '/* header */\npackage foo;\n\nclass A {}\n'


def test_inserts_newline_before_glued_import(tmp_path):
  f = tmp_path / 'A.java'
  f.write_text('/* header */import java.util.List;\n\nclass A {}\n')
  _unglue_headers(tmp_path)
  assert f.read_text() == '/* header */\nimport java.util.List;\n\nclass A {}\n'


def test_leaves_well_formed_files_untouched(tmp_path):
  f = tmp_path / 'A.java'
  original = '/* header */\npackage foo;\n\nclass A {}\n'
  f.write_text(original)
  _unglue_headers(tmp_path)
  assert f.read_text() == original


def test_recurses_into_subdirectories(tmp_path):
  sub = tmp_path / 'pkg'
  sub.mkdir()
  f = sub / 'B.java'
  f.write_text('/* header */package pkg;\n')
  _unglue_headers(tmp_path)
  assert f.read_text() == '/* header */\npackage pkg;\n'
