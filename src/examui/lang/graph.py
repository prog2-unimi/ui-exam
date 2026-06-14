# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

"""Pure graph algorithms and Java class triviality classification.

No I/O, no Flask, no config dependency — importable standalone for unit tests.
"""

from __future__ import annotations

# ── triviality ────────────────────────────────────────────────────────────────


def is_trivial_package(rel_parts: tuple[str, ...], trivial_packages: frozenset[str]) -> bool:
  pkg = '.'.join(rel_parts)
  return any(pkg == tp or pkg.startswith(tp + '.') for tp in trivial_packages)


def is_trivial(stem: str, uses: dict[str, set[str]]) -> bool:
  if stem.endswith(('Exception', 'Error', 'Client')):
    return True
  return any(
    fqn.rsplit('.', 1)[-1].endswith(('Exception', 'Error', 'Throwable'))
    for fqn in uses.get('inherits', set())
  )


def close_trivial(parsed: dict[str, dict]) -> None:
  """Propagate trivial flag transitively: if a superclass is trivial, the subclass is too."""
  changed = True
  while changed:
    changed = False
    for info in parsed.values():
      if not info['trivial']:
        for inh in info['uses'].get('inherits', set()):
          if parsed.get(inh, {}).get('trivial', False):
            info['trivial'] = True
            changed = True
            break


# ── graph algorithms ──────────────────────────────────────────────────────────


def tarjan_sccs(nodes: list[str], adj: dict[str, list[str]]) -> list[list[str]]:
  """Tarjan's SCC algorithm. Returns SCCs in topological order (foundations first)."""
  index_counter = [0]
  stack: list[str] = []
  lowlink: dict[str, int] = {}
  index: dict[str, int] = {}
  on_stack: dict[str, bool] = {}
  sccs: list[list[str]] = []

  def _visit(v: str) -> None:
    index[v] = lowlink[v] = index_counter[0]
    index_counter[0] += 1
    stack.append(v)
    on_stack[v] = True
    for w in adj.get(v, []):
      if w not in index:
        _visit(w)
        lowlink[v] = min(lowlink[v], lowlink[w])
      elif on_stack.get(w):
        lowlink[v] = min(lowlink[v], index[w])
    if lowlink[v] == index[v]:
      scc: list[str] = []
      while True:
        w = stack.pop()
        on_stack[w] = False
        scc.append(w)
        if w == v:
          break
      sccs.append(scc)

  for v in nodes:
    if v not in index:
      _visit(v)

  # Tarjan naturally emits sink SCCs first (foundations-first) — no reversal needed
  return sccs


def transitive_reduction(
  nodes: list[str], adj: dict[str, list[str]], sccs: list[list[str]]
) -> dict[str, list[str]]:
  """Remove inter-SCC edges made redundant by transitivity; intra-SCC edges are kept as-is."""
  node_to_scc: dict[str, int] = {}
  for i, scc in enumerate(sccs):
    for n in scc:
      node_to_scc[n] = i

  n_sccs = len(sccs)

  # Build condensation: cond[i] = set of SCC indices directly reachable from SCC i
  # SCCs from Tarjan are in topological order (foundations first = lower indices),
  # so all edges in the condensation go from higher to lower indices.
  cond: dict[int, set[int]] = {i: set() for i in range(n_sccs)}
  for u in nodes:
    for v in adj.get(u, []):
      si, sj = node_to_scc[u], node_to_scc[v]
      if si != sj:
        cond[si].add(sj)

  # Full reachability in condensation — process ascending (successors always lower-indexed)
  reach: dict[int, set[int]] = {i: set() for i in range(n_sccs)}
  for i in range(n_sccs):
    for j in cond[i]:
      reach[i].add(j)
      reach[i].update(reach[j])

  # Keep condensation edge (i→j) only if j is not reachable via any other direct successor
  cond_keep: set[tuple[int, int]] = set()
  for i in range(n_sccs):
    for j in cond[i]:
      if not any(j in reach[k] for k in cond[i] if k != j):
        cond_keep.add((i, j))

  # Rebuild node-level adjacency
  reduced: dict[str, list[str]] = {u: [] for u in nodes}
  for u in nodes:
    for v in adj.get(u, []):
      si, sj = node_to_scc[u], node_to_scc[v]
      if si == sj or (si, sj) in cond_keep:
        reduced[u].append(v)
  return reduced
