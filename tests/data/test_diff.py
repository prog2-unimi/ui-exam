# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

import zipfile

import pytest

from examui.data.diff import align_lines, extract_backup_consegna, list_sessions_with_submission


@pytest.fixture
def backup_dir(tmp_path):
  with zipfile.ZipFile(tmp_path / '250101.zip', 'w') as zf:
    zf.writestr('alice@example.com/000-consegna.zip', 'v0')
    zf.writestr('alice@example.com/001-consegna.zip', 'v1')
    zf.writestr('alice2@example.com/000-consegna.zip', 'alice2-v0')
  return tmp_path


def test_default_attempt_is_the_last_one(backup_dir, tmp_path):
  dest = tmp_path / 'out.zip'
  used = extract_backup_consegna(backup_dir, '250101', 'alice', None, dest)
  assert used == 1
  assert dest.read_bytes() == b'v1'


def test_explicit_attempt_is_honored(backup_dir, tmp_path):
  dest = tmp_path / 'out.zip'
  used = extract_backup_consegna(backup_dir, '250101', 'alice', 0, dest)
  assert used == 0
  assert dest.read_bytes() == b'v0'


def test_unknown_attempt_raises_with_available_list(backup_dir, tmp_path):
  with pytest.raises(ValueError, match=r'available: 0, 1'):
    extract_backup_consegna(backup_dir, '250101', 'alice', 5, tmp_path / 'out.zip')


def test_unknown_student_raises(backup_dir, tmp_path):
  with pytest.raises(FileNotFoundError, match='No submission by'):
    extract_backup_consegna(backup_dir, '250101', 'carol', None, tmp_path / 'out.zip')


def test_unknown_session_raises(backup_dir, tmp_path):
  with pytest.raises(FileNotFoundError, match='No backup archive'):
    extract_backup_consegna(backup_dir, '999999', 'alice', None, tmp_path / 'out.zip')


def test_email_matching_is_exact_not_prefix(backup_dir, tmp_path):
  dest = tmp_path / 'out.zip'
  used = extract_backup_consegna(backup_dir, '250101', 'alice2', None, dest)
  assert used == 0
  assert dest.read_bytes() == b'alice2-v0'


@pytest.fixture
def multi_session_backup_dir(tmp_path):
  with zipfile.ZipFile(tmp_path / '250101.zip', 'w') as zf:
    zf.writestr('alice@example.com/000-consegna.zip', 'v0')
  with zipfile.ZipFile(tmp_path / '250201.zip', 'w') as zf:
    zf.writestr('bob@example.com/000-consegna.zip', 'bob-v0')
  with zipfile.ZipFile(tmp_path / '250301.zip', 'w') as zf:
    zf.writestr('alice@example.com/000-consegna.zip', 'v1')
  return tmp_path


def test_list_sessions_with_submission_most_recent_first(multi_session_backup_dir):
  assert list_sessions_with_submission(multi_session_backup_dir, 'alice') == ['250301', '250101']


def test_list_sessions_with_submission_empty_for_unknown_student(multi_session_backup_dir):
  assert list_sessions_with_submission(multi_session_backup_dir, 'carol') == []


def test_align_lines_wholly_identical_collapses_to_one_skip():
  # Real callers only diff files already known to differ (classify_files
  # filters those out first) -- this is just the degenerate single-opcode case.
  rows = align_lines(['a', 'b', 'c'], ['a', 'b', 'c'], context=2)
  assert rows == [{'kind': 'skip', 'count': 3}]


def test_align_lines_keeps_context_around_a_change():
  # 7 lines, one changed in the middle, context=2: line 1 and line 7 are each
  # more than `context` lines away from the change, so they collapse.
  old = ['a', 'b', 'c', 'X', 'd', 'e', 'f']
  new = ['a', 'b', 'c', 'Y', 'd', 'e', 'f']
  rows = align_lines(old, new, context=2)
  assert rows == [
    {'kind': 'skip', 'count': 1},
    {'kind': 'equal', 'old_no': 2, 'new_no': 2},
    {'kind': 'equal', 'old_no': 3, 'new_no': 3},
    {'kind': 'replace', 'old_no': 4, 'new_no': 4},
    {'kind': 'equal', 'old_no': 5, 'new_no': 5},
    {'kind': 'equal', 'old_no': 6, 'new_no': 6},
    {'kind': 'skip', 'count': 1},
  ]


def test_align_lines_collapses_long_unchanged_runs():
  old = ['x'] * 10
  new = ['x'] * 5 + ['CHANGED'] + ['x'] * 4
  rows = align_lines(old, new, context=2)
  kinds = [(r['kind'], r.get('count')) for r in rows]
  assert ('skip', None) not in kinds  # sanity: skip rows carry a count
  assert any(k == 'skip' for k, _ in kinds)
  assert sum(c for k, c in kinds if k == 'skip') < len(old)


def test_align_lines_replace_pads_shorter_side():
  rows = align_lines(['a', 'b', 'c'], ['x'], context=2)
  assert rows == [
    {'kind': 'replace', 'old_no': 1, 'new_no': 1},
    {'kind': 'replace', 'old_no': 2, 'new_no': None},
    {'kind': 'replace', 'old_no': 3, 'new_no': None},
  ]


def test_align_lines_pure_insert_and_delete():
  rows = align_lines(['a'], ['a', 'b'], context=2)
  assert rows == [
    {'kind': 'equal', 'old_no': 1, 'new_no': 1},
    {'kind': 'insert', 'old_no': None, 'new_no': 2},
  ]
  rows2 = align_lines(['a', 'b'], ['a'], context=2)
  assert rows2 == [
    {'kind': 'equal', 'old_no': 1, 'new_no': 1},
    {'kind': 'delete', 'old_no': 2, 'new_no': None},
  ]
