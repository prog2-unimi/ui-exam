# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

"""Java source parsing via tree-sitter.

No dependency on Flask or config — importable standalone for unit tests.

Public API
----------
symbols(text)   → list of {kind, name, line, anchor} dicts for the source navigator
class_uses(text) → (package, simple_name, uses) where uses = {member|parameter|return: set[FQN]}
"""

from __future__ import annotations

import tree_sitter_java as _tsjava
from tree_sitter import Language, Parser

_JAVA_LANG = Language(_tsjava.language())
_PARSER = Parser(_JAVA_LANG)

_DECL_NODES = frozenset(
  {
    'class_declaration',
    'interface_declaration',
    'enum_declaration',
    'record_declaration',
    'method_declaration',
    'constructor_declaration',
  }
)

_PRIMITIVES = frozenset(
  {
    'int',
    'long',
    'double',
    'float',
    'boolean',
    'char',
    'byte',
    'short',
    'void',
  }
)

# java.lang is implicitly imported — resolve these without package prefix lookup
_JAVA_LANG = frozenset(
  {
    'Object',
    'String',
    'StringBuilder',
    'StringBuffer',
    'Number',
    'Integer',
    'Long',
    'Double',
    'Float',
    'Boolean',
    'Byte',
    'Short',
    'Character',
    'Math',
    'System',
    'Class',
    'Enum',
    'Record',
    'Thread',
    'Runnable',
    'Iterable',
    'Comparable',
    'Cloneable',
    'Throwable',
    'Exception',
    'RuntimeException',
    'Error',
    'IllegalArgumentException',
    'IllegalStateException',
    'NullPointerException',
    'IndexOutOfBoundsException',
    'UnsupportedOperationException',
    'ArithmeticException',
    'ClassCastException',
    'StackOverflowError',
    'Override',
    'Deprecated',
    'FunctionalInterface',
    'SuppressWarnings',
  }
)

_NAME_TYPES = frozenset({'scoped_identifier', 'identifier'})


# ── internal helpers ──────────────────────────────────────────────────────────


def _file_context(root_node, src: bytes) -> tuple[str, dict[str, str]]:
  """Return (package, {SimpleName: FQN}) from package/import declarations."""
  package = ''
  imports: dict[str, str] = {}
  for child in root_node.children:
    if child.type == 'package_declaration':
      for c in child.children:
        if c.type in _NAME_TYPES:
          package = src[c.start_byte : c.end_byte].decode()
          break
    elif child.type == 'import_declaration':
      for c in child.children:
        if c.type in _NAME_TYPES:
          fqn = src[c.start_byte : c.end_byte].decode()
          simple = fqn.rsplit('.', 1)[-1]
          imports[simple] = fqn
          break
  return package, imports


def _resolve(simple: str, package: str, imports: dict[str, str]) -> str:
  """Map a simple type name to the FQN Javadoc uses in anchors."""
  if not simple or '.' in simple or simple in _PRIMITIVES:
    return simple
  if simple in _JAVA_LANG:
    return f'java.lang.{simple}'
  if simple in imports:
    return imports[simple]
  return f'{package}.{simple}' if package else simple


def _type_text(node, src: bytes) -> str:
  """Erased (no generics) raw type text from a type node."""
  raw = src[node.start_byte : node.end_byte].decode(errors='replace').strip()
  return raw.split('<')[0].strip()


def _params_str(params_node, src: bytes, package: str, imports: dict[str, str]) -> str:
  """Comma-separated FQN parameter types for a Javadoc anchor."""
  types = []
  for child in params_node.children:
    if child.type in ('formal_parameter', 'spread_parameter'):
      t = child.child_by_field_name('type')
      if t:
        types.append(_resolve(_type_text(t, src), package, imports))
  return ','.join(types)


def _collect_symbols(node, src: bytes, out: list, package: str, imports: dict[str, str]) -> None:
  if node.type in _DECL_NODES:
    name_node = node.child_by_field_name('name')
    if name_node:
      name = src[name_node.start_byte : name_node.end_byte].decode()
      line = node.start_point[0] + 1
      kind = node.type.split('_')[0]
      if kind in ('method', 'constructor'):
        p = node.child_by_field_name('parameters')
        anchor = f'{name}({_params_str(p, src, package, imports) if p else ""})'
      else:
        anchor = ''
      out.append({'kind': kind, 'name': name, 'line': line, 'anchor': anchor})
  for child in node.children:
    _collect_symbols(child, src, out, package, imports)


def _collect_type_refs(node, src: bytes) -> list[str]:
  """Recursively collect type references from a type expression.

  Returns simple names for simple types (resolved later by _resolve) and full
  dotted names for scoped types (already fully qualified, _resolve passes them through).
  """
  if node.type == 'type_identifier':
    return [src[node.start_byte : node.end_byte].decode()]
  if node.type == 'scoped_type_identifier':
    # Already fully qualified — return the whole name, strip any generic args
    raw = src[node.start_byte : node.end_byte].decode(errors='replace')
    return [raw.split('<')[0].strip()]
  return [r for child in node.children for r in _collect_type_refs(child, src)]


def _param_refs(params_node, src: bytes, package: str, imports: dict) -> list[str]:
  refs = []
  if not params_node:
    return refs
  for p in params_node.children:
    if p.type in ('formal_parameter', 'spread_parameter'):
      t = p.child_by_field_name('type')
      if t:
        for r in _collect_type_refs(t, src):
          refs.append(_resolve(r, package, imports))
  return refs


def _walk_uses(node, src: bytes, package: str, imports: dict, uses: dict) -> None:
  t = node.type
  if t == 'field_declaration':
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['member'].add(_resolve(r, package, imports))
  elif t in ('method_declaration', 'interface_method_declaration'):
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['return'].add(_resolve(r, package, imports))
    for r in _param_refs(node.child_by_field_name('parameters'), src, package, imports):
      uses['parameter'].add(r)
    # fall through — recurse into body for local vars / new expressions
  elif t in ('constructor_declaration', 'compact_constructor_declaration'):
    for r in _param_refs(node.child_by_field_name('parameters'), src, package, imports):
      uses['parameter'].add(r)
    # fall through — recurse into body
  elif t == 'record_declaration':
    for r in _param_refs(node.child_by_field_name('parameters'), src, package, imports):
      uses['member'].add(r)
    _collect_inherits(node, src, package, imports, uses)
  elif t in ('class_declaration', 'interface_declaration', 'enum_declaration'):
    _collect_inherits(node, src, package, imports, uses)
  elif t == 'type_parameter':
    for child in node.children:
      if child.type == 'type_bound':
        for r in _collect_type_refs(child, src):
          uses['bound'].add(_resolve(r, package, imports))
  elif t == 'local_variable_declaration':
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['local'].add(_resolve(r, package, imports))
  elif t == 'object_creation_expression':
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['instantiates'].add(_resolve(r, package, imports))
  for child in node.children:
    _walk_uses(child, src, package, imports, uses)


def _collect_inherits(node, src: bytes, package: str, imports: dict, uses: dict) -> None:
  """Extract superclass / implemented-interface types from a type declaration.

  class/enum/record use named fields 'superclass' and 'interfaces'.
  interface uses an unnamed child node of type 'extends_interfaces'.
  """
  for field in ('superclass', 'interfaces'):
    f = node.child_by_field_name(field)
    if f:
      for r in _collect_type_refs(f, src):
        uses['inherits'].add(_resolve(r, package, imports))
  # interface_declaration only: extends_interfaces is an unnamed child
  for child in node.children:
    if child.type == 'extends_interfaces':
      for r in _collect_type_refs(child, src):
        uses['inherits'].add(_resolve(r, package, imports))
      break


# ── public API ────────────────────────────────────────────────────────────────


def symbols(text: str) -> list[dict]:
  """Parse Java source and return symbol list for the source navigator.

  Each entry: {kind: str, name: str, line: int, anchor: str}
  anchor is 'name(FQN1,FQN2)' for methods/constructors, '' for type declarations.
  """
  src = text.encode('utf-8')
  tree = _PARSER.parse(src)
  package, imports = _file_context(tree.root_node, src)
  out: list[dict] = []
  _collect_symbols(tree.root_node, src, out, package, imports)
  out.sort(key=lambda s: s['line'])
  return out


def class_uses(text: str) -> tuple[str, str, dict[str, set[str]], int]:
  """Parse Java source and return dependency information.

  Returns (package, simple_class_name, uses, symbol_count) where
  uses = {'member': set[FQN], 'parameter': set[FQN], 'return': set[FQN],
          'inherits': set[FQN], 'bound': set[FQN],
          'local': set[FQN], 'instantiates': set[FQN]}.
  Returns ('', '', empty_uses, 0) if no top-level class/interface/enum/record found.
  """
  _empty_uses: dict[str, set[str]] = {
    'member': set(),
    'parameter': set(),
    'return': set(),
    'inherits': set(),
    'bound': set(),
    'local': set(),
    'instantiates': set(),
  }
  src = text.encode('utf-8')
  tree = _PARSER.parse(src)
  package, imports = _file_context(tree.root_node, src)

  top = next(
    (
      c
      for c in tree.root_node.children
      if c.type
      in ('class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration')
    ),
    None,
  )
  if not top:
    return package, '', _empty_uses, 0

  name_node = top.child_by_field_name('name')
  if not name_node:
    return package, '', _empty_uses, 0

  simple = src[name_node.start_byte : name_node.end_byte].decode()
  uses: dict[str, set[str]] = {
    'member': set(),
    'parameter': set(),
    'return': set(),
    'inherits': set(),
    'bound': set(),
    'local': set(),
    'instantiates': set(),
  }
  _walk_uses(tree.root_node, src, package, imports, uses)
  sym_count = len(symbols(text))
  return package, simple, uses, sym_count
