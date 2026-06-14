# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from __future__ import annotations

import logging
import re
from functools import cache
from pathlib import Path

import graphviz as _graphviz
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import JavaLexer

from examui import config
from examui.lang import graph as _graph
from examui.lang import parsing

_log = logging.getLogger(__name__)


# ── javadoc ───────────────────────────────────────────────────────────────────


def javadoc_root(email: str) -> Path:
  return config.STUDENT_BASE / email / 'javadoc'


# ── source ────────────────────────────────────────────────────────────────────


def _root(email: str) -> Path:
  base = config.STUDENT_BASE / email / 'source'
  java = base / 'src' / 'main' / 'java'
  return java if java.exists() else base


@cache
def tree(email: str) -> list:
  root = _root(email)
  if not root.exists():
    return []
  trivial_paths = _trivial_rel_paths(root)
  return _walk(root, root, trivial_paths)


@cache
def all_symbols(email: str) -> list[dict]:
  root = _root(email)
  if not root.exists():
    return []
  trivial_paths = _trivial_rel_paths(root)
  result = []
  for f in sorted(root.rglob('*.java')):
    if f.stem == 'package-info':
      continue
    rel = str(f.relative_to(root))
    if rel in trivial_paths:
      continue
    if _graph.is_trivial_package(f.relative_to(root).parts[:-1], config.TRIVIAL_PACKAGES):
      continue
    try:
      text = f.read_text(errors='replace')
      for sym in parsing.symbols(text):
        result.append({'file': rel, **sym})
    except Exception:
      pass
  return result


def _walk(path: Path, root: Path, trivial_paths: set[str], parent_trivial: bool = False) -> list:
  items = []
  try:
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
  except PermissionError:
    return []
  for entry in entries:
    rel = str(entry.relative_to(root))
    if entry.is_dir():
      trivial = parent_trivial or _graph.is_trivial_package(entry.relative_to(root).parts, config.TRIVIAL_PACKAGES)
      children = _walk(entry, root, trivial_paths, trivial)
      if children:
        items.append(
          {'type': 'dir', 'name': entry.name, 'path': rel, 'children': children, 'trivial': trivial}
        )
    elif entry.suffix == '.java':
      if entry.stem == 'package-info':
        continue
      trivial = parent_trivial or rel in trivial_paths
      items.append({'type': 'file', 'name': entry.name, 'path': rel, 'trivial': trivial})
  return items


_LEXER = JavaLexer()
_FORMATTER = HtmlFormatter(linenos=False, cssclass='src', style='default')


def pygments_css() -> str:
  return _FORMATTER.get_style_defs('.src')


def _split_html_lines(html: str) -> list[str]:
  pre = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL)
  if not pre:
    return []
  content = pre.group(1)
  if content.endswith('\n'):
    content = content[:-1]

  result: list[str] = []
  open_spans: list[str] = []

  for raw in content.split('\n'):
    line = ''.join(f'<span{a}>' for a in open_spans) + raw
    for tag in re.findall(r'</?span[^>]*>', raw):
      if tag.startswith('</'):
        if open_spans:
          open_spans.pop()
      else:
        m = re.match(r'<span([^>]*)>', tag)
        if m:
          open_spans.append(m.group(1))
    line += '</span>' * len(open_spans)
    result.append(line)

  return result


@cache
def _trivial_rel_paths(root: Path) -> set[str]:
  """Return root-relative paths of all trivial .java files (by name or inheritance closure)."""
  parsed: dict[str, dict] = {}
  for f in root.rglob('*.java'):
    if f.stem == 'package-info':
      continue
    if _graph.is_trivial_package(f.relative_to(root).parts[:-1], config.TRIVIAL_PACKAGES):
      continue
    try:
      text = f.read_text(errors='replace')
      pkg, simple, uses, _, _kind = parsing.class_uses(text)
      if not simple:
        continue
      fqn = f'{pkg}.{simple}' if pkg else simple
      parsed[fqn] = {
        'rel': str(f.relative_to(root)),
        'uses': uses,
        'trivial': _graph.is_trivial(simple, uses),
      }
    except Exception:
      pass
  _graph.close_trivial(parsed)
  return {info['rel'] for info in parsed.values() if info['trivial']}


_NID_RE = re.compile(r'[^a-zA-Z0-9_]')


def _nid(fqn: str) -> str:
  return 'n_' + _NID_RE.sub('_', fqn)


def _javadoc_ids(email: str, relpath: str) -> frozenset[str]:
  jd_rel = javadoc_path_for_source(relpath)
  if not jd_rel:
    return frozenset()
  jd_path = javadoc_root(email) / jd_rel
  if not jd_path.exists():
    return frozenset()
  return frozenset(re.findall(r'\bid="([^"]*)"', jd_path.read_text(errors='replace')))


@cache
def file(email: str, relpath: str) -> dict | None:
  root = _root(email).resolve()
  path = (root / relpath).resolve()
  if not str(path).startswith(str(root)) or not path.exists() or path.suffix != '.java':
    return None
  text = path.read_text(errors='replace')
  html = highlight(text, _LEXER, _FORMATTER)
  syms = parsing.symbols(text)
  jd_ids = _javadoc_ids(email, relpath)
  if jd_ids:
    for s in syms:
      if s['anchor'] and s['anchor'] not in jd_ids:
        s['anchor'] = ''
  return {
    'lines': _split_html_lines(html),
    'symbols': syms,
  }


@cache
def deps(email: str) -> dict:
  root = _root(email)
  if not root.exists():
    return {'svg': '', 'paths': {}}

  java_files = [
    f
    for f in sorted(root.rglob('*.java'))
    if f.stem != 'package-info'
    and not _graph.is_trivial_package(f.relative_to(root).parts[:-1], config.TRIVIAL_PACKAGES)
  ]

  # Pass 1: parse all files
  all_parsed: dict[str, dict] = {}
  for f in java_files:
    text = f.read_text(errors='replace')
    pkg, simple, uses, sym_count, kind = parsing.class_uses(text)
    if not simple:
      continue
    fqn = f'{pkg}.{simple}' if pkg else simple
    all_parsed[fqn] = {
      'name': simple,
      'path': str(f.relative_to(root)),
      'uses': uses,
      'sym_count': sym_count,
      'kind': kind,
      'trivial': _graph.is_trivial(simple, uses),
    }

  # Pass 2: propagate trivial flag through inheritance chains
  _graph.close_trivial(all_parsed)

  class_info = {fqn: info for fqn, info in all_parsed.items() if not info['trivial']}
  known = set(class_info)

  # Build adjacency list (edges to known classes only, no self-loops)
  adj: dict[str, list[str]] = {fqn: [] for fqn in known}
  for src_fqn, info in class_info.items():
    seen: set[str] = set()
    for targets in info['uses'].values():
      for tgt in targets:
        if tgt in known and tgt != src_fqn and tgt not in seen:
          adj[src_fqn].append(tgt)
          seen.add(tgt)

  # Out-degree per node (original graph, used for within-SCC ordering)
  out_degree = {fqn: len(neighbours) for fqn, neighbours in adj.items()}

  sccs = _graph.tarjan_sccs(list(known), adj)
  adj_reduced = _graph.transitive_reduction(list(known), adj, sccs)

  # Within each SCC sort ascending by (out_degree, sym_count) — simplest first
  for scc in sccs:
    scc.sort(key=lambda fqn: (out_degree[fqn], class_info[fqn]['sym_count']))

  _KIND_FILL = {
    'class':     'white',
    'abstract':  '#f0f0f0',
    'interface': '#ddeeff',
    'record':    '#ddffdd',
    'enum':      '#fde8d0',
  }

  # Build Graphviz graph
  dot = _graphviz.Digraph(
    graph_attr={
      'rankdir': 'LR',
      'splines': 'spline',
      'bgcolor': 'transparent',
      'nodesep': '0.2',
      'ranksep': '0.4',
    },
    node_attr={
      'shape': 'box',
      'fontname': 'Courier',
      'style': 'filled',
      'fillcolor': 'white',
      'fontsize': '7',
      'margin': '0.03,0.02',
      'height': '0.15',
    },
    edge_attr={'arrowsize': '0.4', 'color': '#888888'},
  )

  paths: dict[str, str] = {}

  for scc_idx, scc in enumerate(sccs):
    if len(scc) == 1:
      fqn = scc[0]
      info = class_info[fqn]
      nid = _nid(fqn)
      dot.node(fqn, label=info['name'], id=nid, tooltip=fqn,
               fillcolor=_KIND_FILL.get(info['kind'], 'white'))
      paths[nid] = info['path']
    else:
      # Multi-node SCC — wrap in a cluster subgraph
      with dot.subgraph(name=f'cluster_{scc_idx}') as sg:
        sg.attr(style='dashed', color='#cccccc', fontsize='7', label='')
        for fqn in scc:
          info = class_info[fqn]
          nid = _nid(fqn)
          sg.node(fqn, label=info['name'], id=nid, tooltip=fqn,
                  fillcolor=_KIND_FILL.get(info['kind'], 'white'))
          paths[nid] = info['path']

  node_to_scc = {fqn: i for i, scc in enumerate(sccs) for fqn in scc}

  # Edges from reduced graph, reversed so foundations become sources (left) in rankdir=LR
  # Intra-SCC edges are omitted from the drawing (the cluster boundary implies the cycle).
  drawn: set[tuple[str, str]] = set()
  for src_fqn in known:
    for tgt in adj_reduced[src_fqn]:
      if (src_fqn, tgt) not in drawn and node_to_scc[src_fqn] != node_to_scc[tgt]:
        dot.edge(tgt, src_fqn)
        drawn.add((src_fqn, tgt))

  svg = dot.pipe(format='svg').decode('utf-8')
  return {'svg': svg, 'paths': paths}


def warmup(email: str) -> None:
  """Populate all caches for one student. Call at startup before workers fork."""
  _log.info('[warmup] %s: tree', email)
  tree(email)
  _log.info('[warmup] %s: symbols', email)
  all_symbols(email)
  _log.info('[warmup] %s: deps', email)
  deps(email)
  _log.info('[warmup] %s: done', email)


def javadoc_path_for_source(relpath: str) -> str | None:
  if relpath.endswith('.java'):
    return relpath[:-5] + '.html'
  return None
