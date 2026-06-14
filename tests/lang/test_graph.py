# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from examui.lang.graph import (
  close_trivial,
  is_trivial,
  is_trivial_package,
  tarjan_sccs,
  transitive_reduction,
)


# ── is_trivial_package ────────────────────────────────────────────────────────


def test_is_trivial_package_exact_match():
  assert is_trivial_package(('com', 'example', 'client'), frozenset({'client'})) is False
  assert is_trivial_package(('client',), frozenset({'client'})) is True


def test_is_trivial_package_prefix_match():
  assert is_trivial_package(('util', 'helper'), frozenset({'util'})) is True


def test_is_trivial_package_no_match():
  assert is_trivial_package(('com', 'example', 'model'), frozenset({'client', 'util'})) is False


def test_is_trivial_package_partial_name_not_matched():
  # 'clients' must not match trivial package 'client'
  assert is_trivial_package(('clients',), frozenset({'client'})) is False


# ── is_trivial ────────────────────────────────────────────────────────────────


def test_is_trivial_exception_suffix():
  assert is_trivial('MyException', {}) is True


def test_is_trivial_error_suffix():
  assert is_trivial('ParseError', {}) is True


def test_is_trivial_client_suffix():
  assert is_trivial('HttpClient', {}) is True


def test_is_trivial_inherits_throwable():
  assert is_trivial('Boom', {'inherits': {'java.lang.Throwable'}}) is True


def test_is_trivial_inherits_exception():
  assert is_trivial('Oops', {'inherits': {'java.lang.Exception'}}) is True


def test_is_trivial_inherits_error():
  assert is_trivial('Bad', {'inherits': {'java.lang.Error'}}) is True


def test_is_trivial_inherits_unrelated():
  assert is_trivial('MyClass', {'inherits': {'com.example.Base'}}) is False


def test_is_trivial_no_inherits():
  assert is_trivial('MyClass', {}) is False


# ── close_trivial ─────────────────────────────────────────────────────────────


def test_close_trivial_direct():
  parsed = {
    'com.example.Base': {'trivial': True, 'uses': {}},
    'com.example.Child': {'trivial': False, 'uses': {'inherits': {'com.example.Base'}}},
  }
  close_trivial(parsed)
  assert parsed['com.example.Child']['trivial'] is True


def test_close_trivial_transitive():
  parsed = {
    'A': {'trivial': True, 'uses': {}},
    'B': {'trivial': False, 'uses': {'inherits': {'A'}}},
    'C': {'trivial': False, 'uses': {'inherits': {'B'}}},
  }
  close_trivial(parsed)
  assert parsed['B']['trivial'] is True
  assert parsed['C']['trivial'] is True


def test_close_trivial_non_trivial_parent():
  parsed = {
    'A': {'trivial': False, 'uses': {}},
    'B': {'trivial': False, 'uses': {'inherits': {'A'}}},
  }
  close_trivial(parsed)
  assert parsed['B']['trivial'] is False


def test_close_trivial_unknown_parent_ignored():
  parsed = {
    'B': {'trivial': False, 'uses': {'inherits': {'Unknown'}}},
  }
  close_trivial(parsed)
  assert parsed['B']['trivial'] is False


# ── tarjan_sccs ───────────────────────────────────────────────────────────────


def test_tarjan_sccs_dag():
  # A → B → C, no cycles — each node is its own SCC, foundations first
  nodes = ['A', 'B', 'C']
  adj = {'A': ['B'], 'B': ['C'], 'C': []}
  sccs = tarjan_sccs(nodes, adj)
  assert len(sccs) == 3
  # topological order: C first (foundation), then B, then A
  flat = [scc[0] for scc in sccs]
  assert flat.index('C') < flat.index('B') < flat.index('A')


def test_tarjan_sccs_simple_cycle():
  nodes = ['A', 'B', 'C']
  adj = {'A': ['B'], 'B': ['C'], 'C': ['A']}
  sccs = tarjan_sccs(nodes, adj)
  assert len(sccs) == 1
  assert set(sccs[0]) == {'A', 'B', 'C'}


def test_tarjan_sccs_two_components():
  # X → Y (cycle) and Z (singleton), Z has no edges to/from X,Y
  nodes = ['X', 'Y', 'Z']
  adj = {'X': ['Y'], 'Y': ['X'], 'Z': []}
  sccs = tarjan_sccs(nodes, adj)
  assert len(sccs) == 2
  scc_sets = [frozenset(s) for s in sccs]
  assert frozenset({'X', 'Y'}) in scc_sets
  assert frozenset({'Z'}) in scc_sets


def test_tarjan_sccs_complex():
  # Graph: A→B, B→C, C→B (cycle B-C), C→D, D→A (cycle A-B-C-D? no: A→B→C→B and C→D→A)
  # SCC1: {A, B, C, D} — all reachable from A back to A via D
  nodes = ['A', 'B', 'C', 'D']
  adj = {'A': ['B'], 'B': ['C'], 'C': ['B', 'D'], 'D': ['A']}
  sccs = tarjan_sccs(nodes, adj)
  assert len(sccs) == 1
  assert set(sccs[0]) == {'A', 'B', 'C', 'D'}


def test_tarjan_sccs_isolated_node():
  nodes = ['A', 'B']
  adj = {'A': [], 'B': []}
  sccs = tarjan_sccs(nodes, adj)
  assert len(sccs) == 2
  assert all(len(s) == 1 for s in sccs)


# ── transitive_reduction ──────────────────────────────────────────────────────


def test_transitive_reduction_removes_redundant():
  # A → B → C, A → C  (A→C is redundant)
  nodes = ['A', 'B', 'C']
  adj = {'A': ['B', 'C'], 'B': ['C'], 'C': []}
  sccs = tarjan_sccs(nodes, adj)
  reduced = transitive_reduction(nodes, adj, sccs)
  assert 'C' not in reduced['A']
  assert 'C' in reduced['B']
  assert 'B' in reduced['A']


def test_transitive_reduction_keeps_direct_edges():
  # Simple chain A → B → C, nothing to reduce
  nodes = ['A', 'B', 'C']
  adj = {'A': ['B'], 'B': ['C'], 'C': []}
  sccs = tarjan_sccs(nodes, adj)
  reduced = transitive_reduction(nodes, adj, sccs)
  assert reduced['A'] == ['B']
  assert reduced['B'] == ['C']
  assert reduced['C'] == []


def test_transitive_reduction_intra_scc_edges_kept():
  # Cycle A → B → A — both edges must be kept (intra-SCC)
  nodes = ['A', 'B']
  adj = {'A': ['B'], 'B': ['A']}
  sccs = tarjan_sccs(nodes, adj)
  reduced = transitive_reduction(nodes, adj, sccs)
  assert 'B' in reduced['A']
  assert 'A' in reduced['B']


def test_transitive_reduction_diamond():
  # A → B, A → C, B → D, C → D  — both A→B and A→C must be kept (no redundancy)
  nodes = ['A', 'B', 'C', 'D']
  adj = {'A': ['B', 'C'], 'B': ['D'], 'C': ['D'], 'D': []}
  sccs = tarjan_sccs(nodes, adj)
  reduced = transitive_reduction(nodes, adj, sccs)
  assert 'B' in reduced['A']
  assert 'C' in reduced['A']
  assert 'D' in reduced['B']
  assert 'D' in reduced['C']
