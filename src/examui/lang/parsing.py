# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

"""Java source parsing via tree-sitter.

No dependency on Flask or config — importable standalone for unit tests.

Public API
----------
symbols(text)    → list of {kind, name, line, anchor} dicts for the source navigator
class_uses(text) → list of {fqn, name, enclosing, kind, uses, sym_count, line} dicts, one
                    per type declaration in the file (top-level and nested, at any depth)
"""

from __future__ import annotations

import tree_sitter_java as _tsjava
from tree_sitter import Language, Parser

_LANG = Language(_tsjava.language())
_PARSER = Parser(_LANG)

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

# Named type declarations — the containment unit for the dependency graph.
# Local classes (declared inside a method/initializer 'block') and anonymous
# class bodies are deliberately out of scope: _scan_body stops at 'block'.
_TYPE_DECL_TYPES = frozenset(
  {'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration'}
)

# Mirrors _DECL_NODES minus the type-decl kinds, so per-type sym_count stays
# consistent with len(symbols(text)) for the (common) case of a file with no nesting.
_MEMBER_SYM_TYPES = frozenset({'method_declaration', 'constructor_declaration'})

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


def _resolve_simple(
  simple: str, package: str, imports: dict[str, str], scope_chain: list[dict[str, str]]
) -> str:
  """Resolve an unqualified simple name: enclosing-type scope, then java.lang, then imports,
  then (as a last-resort guess) same package."""
  for scope in scope_chain:
    if simple in scope:
      return scope[simple]
  if simple in _JAVA_LANG:
    return f'java.lang.{simple}'
  if simple in imports:
    return imports[simple]
  return f'{package}.{simple}' if package else simple


def _resolve(
  simple: str, package: str, imports: dict[str, str], scope_chain: list[dict[str, str]]
) -> str:
  """Map a simple or dotted type name to the FQN Javadoc uses in anchors.

  A dotted name (e.g. 'Outer.Inner' or 'java.util.List') is either an already
  fully-qualified path, or a locally-visible/imported simple name followed by
  nested-type segments. We can't tell these apart from syntax alone, so we use
  the same PascalCase-vs-lowercase convention the static-access heuristic below
  relies on: an uppercase first segment is treated as a resolvable type name
  (scope/java.lang/imports, else same-package guess); a lowercase first segment
  is assumed to already be a package path and passed through unchanged.
  """
  if not simple or simple in _PRIMITIVES:
    return simple
  if '.' in simple:
    head, rest = simple.split('.', 1)
    if not head[:1].isupper():
      return simple
    return f'{_resolve_simple(head, package, imports, scope_chain)}.{rest}'
  return _resolve_simple(simple, package, imports, scope_chain)


def _type_text(node, src: bytes) -> str:
  """Erased (no generics) raw type text from a type node."""
  raw = src[node.start_byte : node.end_byte].decode(errors='replace').strip()
  return raw.split('<')[0].strip()


def _params_str(params_node, src: bytes, package: str, imports: dict[str, str]) -> str:
  """Comma-separated FQN parameter types for a Javadoc anchor.

  Used only by the (unscoped, file-flat) symbol navigator — scope_chain is
  intentionally empty here, matching pre-nesting-support behaviour.
  """
  types = []
  for child in params_node.children:
    if child.type in ('formal_parameter', 'spread_parameter'):
      t = child.child_by_field_name('type')
      if t:
        types.append(_resolve(_type_text(t, src), package, imports, []))
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
  dotted names for scoped types (resolved later by _resolve too — see its docstring).
  """
  if node.type == 'type_identifier':
    return [src[node.start_byte : node.end_byte].decode()]
  if node.type == 'scoped_type_identifier':
    raw = src[node.start_byte : node.end_byte].decode(errors='replace')
    return [raw.split('<')[0].strip()]
  return [r for child in node.children for r in _collect_type_refs(child, src)]


def _param_refs(
  params_node, src: bytes, package: str, imports: dict, scope_chain: list[dict[str, str]]
) -> list[str]:
  refs = []
  if not params_node:
    return refs
  for p in params_node.children:
    if p.type in ('formal_parameter', 'spread_parameter'):
      t = p.child_by_field_name('type')
      if t:
        for r in _collect_type_refs(t, src):
          refs.append(_resolve(r, package, imports, scope_chain))
  return refs


def _walk_uses(
  node, src: bytes, package: str, imports: dict, scope_chain: list[dict[str, str]], uses: dict, root
) -> None:
  t = node.type
  if t == 'field_declaration':
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['member'].add(_resolve(r, package, imports, scope_chain))
  elif t in ('method_declaration', 'interface_method_declaration'):
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['return'].add(_resolve(r, package, imports, scope_chain))
    for r in _param_refs(node.child_by_field_name('parameters'), src, package, imports, scope_chain):
      uses['parameter'].add(r)
    # fall through — recurse into body for local vars / new expressions
  elif t in ('constructor_declaration', 'compact_constructor_declaration'):
    for r in _param_refs(node.child_by_field_name('parameters'), src, package, imports, scope_chain):
      uses['parameter'].add(r)
    # fall through — recurse into body
  elif t == 'record_declaration':
    if node is not root:
      return  # nested type — handled by its own top-level _walk_uses call
    for r in _param_refs(node.child_by_field_name('parameters'), src, package, imports, scope_chain):
      uses['member'].add(r)
    _collect_inherits(node, src, package, imports, scope_chain, uses)
  elif t in ('class_declaration', 'interface_declaration', 'enum_declaration'):
    if node is not root:
      return  # nested type — handled by its own top-level _walk_uses call
    _collect_inherits(node, src, package, imports, scope_chain, uses)
  elif t == 'type_parameter':
    for child in node.children:
      if child.type == 'type_bound':
        for r in _collect_type_refs(child, src):
          uses['bound'].add(_resolve(r, package, imports, scope_chain))
  elif t == 'local_variable_declaration':
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['local'].add(_resolve(r, package, imports, scope_chain))
  elif t == 'object_creation_expression':
    typ = node.child_by_field_name('type')
    if typ:
      for r in _collect_type_refs(typ, src):
        uses['instantiates'].add(_resolve(r, package, imports, scope_chain))
  elif t in ('method_invocation', 'field_access'):
    obj = node.child_by_field_name('object')
    if obj and obj.type == 'identifier':
      name = src[obj.start_byte : obj.end_byte].decode()
      if name[:1].isupper():
        uses['local'].add(_resolve(name, package, imports, scope_chain))
  for child in node.children:
    _walk_uses(child, src, package, imports, scope_chain, uses, root)


def _collect_inherits(
  node, src: bytes, package: str, imports: dict, scope_chain: list[dict[str, str]], uses: dict
) -> None:
  """Extract superclass / implemented-interface types from a type declaration.

  class/enum/record use named fields 'superclass' and 'interfaces'.
  interface uses an unnamed child node of type 'extends_interfaces'.
  """
  for field in ('superclass', 'interfaces'):
    f = node.child_by_field_name(field)
    if f:
      for r in _collect_type_refs(f, src):
        uses['inherits'].add(_resolve(r, package, imports, scope_chain))
  # interface_declaration only: extends_interfaces is an unnamed child
  for child in node.children:
    if child.type == 'extends_interfaces':
      for r in _collect_type_refs(child, src):
        uses['inherits'].add(_resolve(r, package, imports, scope_chain))
      break


def _decl_kind(node, src: bytes) -> str:
  _KIND_MAP = {
    'interface_declaration': 'interface',
    'enum_declaration':      'enum',
    'record_declaration':    'record',
  }
  if node.type in _KIND_MAP:
    return _KIND_MAP[node.type]
  mods = node.child_by_field_name('modifiers')
  is_abstract = mods and any(
    src[c.start_byte : c.end_byte].decode() == 'abstract' for c in mods.children
  )
  return 'abstract' if is_abstract else 'class'


def _scan_body(node) -> tuple[list, list]:
  """Return (nested_type_decls, member_decls) directly inside a type's body.

  Does not cross into method/constructor/initializer bodies ('block') — this is
  what keeps local classes and their members out of scope — nor past a nested
  type declaration's own body (that subtree is handled by its own recursive
  _build_records call). Wrapper nodes (e.g. enum_body_declarations) are
  transparent: the walk simply continues through anything else.
  """
  types: list = []
  members: list = []
  for child in node.children:
    if child.type in _TYPE_DECL_TYPES:
      types.append(child)
    elif child.type in _MEMBER_SYM_TYPES:
      members.append(child)
    elif child.type == 'block':
      continue
    else:
      t2, m2 = _scan_body(child)
      types.extend(t2)
      members.extend(m2)
  return types, members


def _empty_uses() -> dict[str, set[str]]:
  return {
    'member': set(),
    'parameter': set(),
    'return': set(),
    'inherits': set(),
    'bound': set(),
    'local': set(),
    'instantiates': set(),
  }


def _build_records(
  node,
  src: bytes,
  package: str,
  imports: dict[str, str],
  enclosing_fqn: str | None,
  scope_chain: list[dict[str, str]],
) -> list[dict]:
  name_node = node.child_by_field_name('name')
  if not name_node:
    return []
  name = src[name_node.start_byte : name_node.end_byte].decode()
  fqn = f'{enclosing_fqn}.{name}' if enclosing_fqn else (f'{package}.{name}' if package else name)

  body = node.child_by_field_name('body')
  nested_type_nodes, member_nodes = _scan_body(body) if body else ([], [])

  own_scope = {name: fqn}
  for nt in nested_type_nodes:
    nt_name_node = nt.child_by_field_name('name')
    if nt_name_node:
      nt_name = src[nt_name_node.start_byte : nt_name_node.end_byte].decode()
      own_scope[nt_name] = f'{fqn}.{nt_name}'
  new_scope_chain = [own_scope, *scope_chain]

  uses = _empty_uses()
  _walk_uses(node, src, package, imports, new_scope_chain, uses, node)

  records = [
    {
      'fqn': fqn,
      'name': name,
      'enclosing': enclosing_fqn,
      'kind': _decl_kind(node, src),
      'uses': uses,
      'sym_count': 1 + len(member_nodes),
      'line': node.start_point[0] + 1,
    }
  ]
  for nt in nested_type_nodes:
    records.extend(_build_records(nt, src, package, imports, fqn, new_scope_chain))
  return records


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


def class_uses(text: str) -> list[dict]:
  """Parse Java source and return dependency information for every type declaration.

  Returns one entry per class/interface/enum/record declared in the file — both
  top-level and nested (static or inner, at any depth). Local classes (declared
  inside a method/initializer body) and anonymous class bodies are not included.

  Each entry: {fqn, name, enclosing, kind, uses, sym_count} where:
    fqn       - fully-qualified name, e.g. 'com.example.Outer.Inner'
    name      - simple name, e.g. 'Inner'
    enclosing - FQN of the immediately containing type, or None for top-level types
    kind      - one of 'class', 'abstract', 'interface', 'enum', 'record'
    uses      - {'member': set[FQN], 'parameter': set[FQN], 'return': set[FQN],
                 'inherits': set[FQN], 'bound': set[FQN],
                 'local': set[FQN], 'instantiates': set[FQN]}
    sym_count - number of methods/constructors declared directly in this type, plus one
    line      - 1-based source line of the type declaration itself

  Returns [] if no type declaration is found.
  """
  src = text.encode('utf-8')
  tree = _PARSER.parse(src)
  package, imports = _file_context(tree.root_node, src)

  top_level_nodes, _ = _scan_body(tree.root_node)
  records: list[dict] = []
  for node in top_level_nodes:
    records.extend(_build_records(node, src, package, imports, None, []))
  return records
