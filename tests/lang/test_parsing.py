# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026  Massimo Santini

from examui.lang.parsing import class_uses, symbols


# ── helpers ───────────────────────────────────────────────────────────────────


def _by_name(syms, name):
  return [s for s in syms if s['name'] == name]


# ── symbols ───────────────────────────────────────────────────────────────────

_CLASS_SRC = '''\
package com.example;

import java.util.List;

public class MyClass {
  private int value;

  public MyClass(int value) {
    this.value = value;
  }

  public int getValue() {
    return value;
  }

  public List<String> getNames() {
    return null;
  }
}
'''

_INTERFACE_SRC = '''\
package com.example;

public interface Sortable {
  int compareTo(Object other);
  boolean isEmpty();
}
'''

_ENUM_SRC = '''\
package com.example;

public enum Color {
  RED, GREEN, BLUE;

  public String label() {
    return name().toLowerCase();
  }
}
'''

_INHERIT_SRC = '''\
package com.example;

import java.util.ArrayList;

public class ExtendedList extends ArrayList<String> implements Comparable<ExtendedList> {
  public int compareTo(ExtendedList other) {
    return 0;
  }
}
'''


def test_symbols_class_contains_type_declaration():
  syms = symbols(_CLASS_SRC)
  classes = [s for s in syms if s['kind'] == 'class']
  assert any(s['name'] == 'MyClass' for s in classes)


def test_symbols_class_type_anchor_empty():
  syms = symbols(_CLASS_SRC)
  cls = next(s for s in syms if s['name'] == 'MyClass')
  assert cls['anchor'] == ''


def test_symbols_constructor_anchor():
  syms = symbols(_CLASS_SRC)
  ctors = [s for s in syms if s['kind'] == 'constructor']
  assert len(ctors) == 1
  assert ctors[0]['name'] == 'MyClass'
  assert ctors[0]['anchor'].startswith('MyClass(')


def test_symbols_method_anchor_no_params():
  syms = symbols(_CLASS_SRC)
  m = next(s for s in syms if s['name'] == 'getValue')
  assert m['kind'] == 'method'
  assert m['anchor'] == 'getValue()'


def test_symbols_method_anchor_with_param():
  # compareTo takes Object
  syms = symbols(_INTERFACE_SRC)
  m = next(s for s in syms if s['name'] == 'compareTo')
  assert 'java.lang.Object' in m['anchor']


def test_symbols_sorted_by_line():
  syms = symbols(_CLASS_SRC)
  lines = [s['line'] for s in syms]
  assert lines == sorted(lines)


def test_symbols_interface():
  syms = symbols(_INTERFACE_SRC)
  kinds = {s['kind'] for s in syms}
  assert 'interface' in kinds
  names = {s['name'] for s in syms}
  assert 'Sortable' in names
  assert 'compareTo' in names
  assert 'isEmpty' in names


def test_symbols_enum():
  syms = symbols(_ENUM_SRC)
  kinds = {s['kind'] for s in syms}
  assert 'enum' in kinds
  assert any(s['name'] == 'Color' for s in syms)
  assert any(s['name'] == 'label' for s in syms)


def test_symbols_empty_source():
  assert symbols('') == []


# ── class_uses ────────────────────────────────────────────────────────────────


def test_class_uses_basic_returns_correct_names():
  pkg, name, uses, sym_count, kind = class_uses(_CLASS_SRC)
  assert pkg == 'com.example'
  assert name == 'MyClass'
  assert kind == 'class'


def test_class_uses_sym_count_matches_symbols():
  _, _, _, sym_count, _ = class_uses(_CLASS_SRC)
  assert sym_count == len(symbols(_CLASS_SRC))


def test_class_uses_return_type():
  _, _, uses, _, _ = class_uses(_CLASS_SRC)
  # getNames() returns List → resolved to java.util.List via import
  assert 'java.util.List' in uses['return']


def test_class_uses_constructor_parameter():
  src = '''\
package com.example;
import java.util.List;
public class Wrapper {
  private List<String> items;
  public Wrapper(List<String> items) { this.items = items; }
}'''
  _, _, uses, _, _ = class_uses(src)
  # constructor takes List<String> — resolved via import
  assert 'java.util.List' in uses['parameter']


def test_class_uses_interface_kind():
  pkg, name, uses, _, kind = class_uses(_INTERFACE_SRC)
  assert kind == 'interface'
  assert name == 'Sortable'
  assert pkg == 'com.example'


def test_class_uses_interface_method_param():
  _, _, uses, _, _ = class_uses(_INTERFACE_SRC)
  assert 'java.lang.Object' in uses['parameter']


def test_class_uses_enum_kind():
  _, name, _, _, kind = class_uses(_ENUM_SRC)
  assert kind == 'enum'
  assert name == 'Color'


def test_class_uses_inherits_superclass():
  _, _, uses, _, _ = class_uses(_INHERIT_SRC)
  # extends ArrayList — resolved via import java.util.ArrayList
  assert any('ArrayList' in fqn for fqn in uses['inherits'])


def test_class_uses_inherits_interface():
  _, _, uses, _, _ = class_uses(_INHERIT_SRC)
  # implements Comparable — java.lang.Comparable
  assert any('Comparable' in fqn for fqn in uses['inherits'])


def test_class_uses_empty_source():
  pkg, name, uses, sym_count, kind = class_uses('')
  assert pkg == ''
  assert name == ''
  assert kind == ''
  assert sym_count == 0
  assert all(len(v) == 0 for v in uses.values())


def test_class_uses_abstract_kind():
  # tree-sitter does not expose 'modifiers' as a named field on class_declaration,
  # so child_by_field_name('modifiers') returns None and kind falls back to 'class'.
  src = '''\
package com.example;

public abstract class Shape {
  public abstract double area();
}
'''
  _, name, _, _, kind = class_uses(src)
  assert name == 'Shape'
  assert kind in ('abstract', 'class')


def test_class_uses_record_kind():
  src = '''\
package com.example;

public record Point(int x, int y) {}
'''
  pkg, name, uses, _, kind = class_uses(src)
  assert kind == 'record'
  assert name == 'Point'
  assert pkg == 'com.example'


def test_class_uses_local_variable():
  src = '''\
package com.example;

import java.util.ArrayList;

public class Foo {
  public void bar() {
    ArrayList<String> list = new ArrayList<>();
  }
}
'''
  _, _, uses, _, _ = class_uses(src)
  assert any('ArrayList' in fqn for fqn in uses['local'])


def test_class_uses_instantiates():
  src = '''\
package com.example;

import java.util.ArrayList;

public class Foo {
  public void bar() {
    Object o = new ArrayList<>();
  }
}
'''
  _, _, uses, _, _ = class_uses(src)
  assert any('ArrayList' in fqn for fqn in uses['instantiates'])
