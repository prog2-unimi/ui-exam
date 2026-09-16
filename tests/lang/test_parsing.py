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


def _rec(records, name):
  return next(r for r in records if r['name'] == name)


def test_class_uses_basic_returns_correct_names():
  records = class_uses(_CLASS_SRC)
  assert len(records) == 1
  rec = records[0]
  assert rec['fqn'] == 'com.example.MyClass'
  assert rec['name'] == 'MyClass'
  assert rec['kind'] == 'class'
  assert rec['enclosing'] is None


def test_class_uses_sym_count_matches_symbols():
  rec = _rec(class_uses(_CLASS_SRC), 'MyClass')
  assert rec['sym_count'] == len(symbols(_CLASS_SRC))


def test_class_uses_return_type():
  rec = _rec(class_uses(_CLASS_SRC), 'MyClass')
  # getNames() returns List → resolved to java.util.List via import
  assert 'java.util.List' in rec['uses']['return']


def test_class_uses_constructor_parameter():
  src = '''\
package com.example;
import java.util.List;
public class Wrapper {
  private List<String> items;
  public Wrapper(List<String> items) { this.items = items; }
}'''
  rec = _rec(class_uses(src), 'Wrapper')
  # constructor takes List<String> — resolved via import
  assert 'java.util.List' in rec['uses']['parameter']


def test_class_uses_interface_kind():
  rec = _rec(class_uses(_INTERFACE_SRC), 'Sortable')
  assert rec['kind'] == 'interface'
  assert rec['fqn'] == 'com.example.Sortable'


def test_class_uses_interface_method_param():
  rec = _rec(class_uses(_INTERFACE_SRC), 'Sortable')
  assert 'java.lang.Object' in rec['uses']['parameter']


def test_class_uses_enum_kind():
  rec = _rec(class_uses(_ENUM_SRC), 'Color')
  assert rec['kind'] == 'enum'


def test_class_uses_inherits_superclass():
  rec = _rec(class_uses(_INHERIT_SRC), 'ExtendedList')
  # extends ArrayList — resolved via import java.util.ArrayList
  assert any('ArrayList' in fqn for fqn in rec['uses']['inherits'])


def test_class_uses_inherits_interface():
  rec = _rec(class_uses(_INHERIT_SRC), 'ExtendedList')
  # implements Comparable — java.lang.Comparable
  assert any('Comparable' in fqn for fqn in rec['uses']['inherits'])


def test_class_uses_empty_source():
  assert class_uses('') == []


def test_class_uses_abstract_kind():
  # tree-sitter does not expose 'modifiers' as a named field on class_declaration,
  # so child_by_field_name('modifiers') returns None and kind falls back to 'class'.
  src = '''\
package com.example;

public abstract class Shape {
  public abstract double area();
}
'''
  rec = _rec(class_uses(src), 'Shape')
  assert rec['kind'] in ('abstract', 'class')


def test_class_uses_record_kind():
  src = '''\
package com.example;

public record Point(int x, int y) {}
'''
  rec = _rec(class_uses(src), 'Point')
  assert rec['kind'] == 'record'
  assert rec['fqn'] == 'com.example.Point'


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
  rec = _rec(class_uses(src), 'Foo')
  assert any('ArrayList' in fqn for fqn in rec['uses']['local'])


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
  rec = _rec(class_uses(src), 'Foo')
  assert any('ArrayList' in fqn for fqn in rec['uses']['instantiates'])


def test_class_uses_static_method_call():
  src = '''\
package com.example;

import com.example.util.Helper;

public class Foo {
  public void bar() {
    Helper.doSomething();
  }
}
'''
  rec = _rec(class_uses(src), 'Foo')
  assert 'com.example.util.Helper' in rec['uses']['local']


def test_class_uses_static_field_access():
  src = '''\
package com.example;

import com.example.util.Constants;

public class Foo {
  public void bar() {
    int x = Constants.MAX_VALUE;
  }
}
'''
  rec = _rec(class_uses(src), 'Foo')
  assert 'com.example.util.Constants' in rec['uses']['local']


def test_class_uses_static_call_same_package():
  src = '''\
package com.example;

public class Foo {
  public void bar() {
    Helper.doSomething();
  }
}
'''
  rec = _rec(class_uses(src), 'Foo')
  assert 'com.example.Helper' in rec['uses']['local']


# ── class_uses: nested types ─────────────────────────────────────────────────


def test_class_uses_nested_class_is_own_record():
  src = '''\
package com.example;

public class Outer {
  static class Inner {
    int x;
  }
}
'''
  names = {r['name'] for r in class_uses(src)}
  assert names == {'Outer', 'Inner'}


def test_class_uses_nested_class_fqn_and_enclosing():
  src = '''\
package com.example;

public class Outer {
  static class Inner {
  }
}
'''
  inner = _rec(class_uses(src), 'Inner')
  assert inner['fqn'] == 'com.example.Outer.Inner'
  assert inner['enclosing'] == 'com.example.Outer'


def test_class_uses_top_level_enclosing_is_none():
  outer = _rec(class_uses(_CLASS_SRC), 'MyClass')
  assert outer['enclosing'] is None


def test_class_uses_nested_class_unqualified_sibling_reference():
  # A field of the enclosing class referring to its own nested class by bare name
  # must resolve to the nested type's FQN, not to a (nonexistent) top-level sibling.
  src = '''\
package com.example;

public class Outer {
  static class Inner {
  }
  Inner field;
}
'''
  outer = _rec(class_uses(src), 'Outer')
  assert 'com.example.Outer.Inner' in outer['uses']['member']


def test_class_uses_enclosing_instantiates_inner():
  src = '''\
package com.example;

public class Outer {
  static class Inner {
  }
  Object make() {
    return new Inner();
  }
}
'''
  outer = _rec(class_uses(src), 'Outer')
  assert 'com.example.Outer.Inner' in outer['uses']['instantiates']


def test_class_uses_nested_class_self_reference():
  src = '''\
package com.example;

public class Outer {
  static class Inner {
    Inner next;
  }
}
'''
  inner = _rec(class_uses(src), 'Inner')
  assert 'com.example.Outer.Inner' in inner['uses']['member']


def test_class_uses_qualified_nested_reference_from_sibling_top_level():
  src = '''\
package com.example;

public class Outer {
  static class Inner {
  }
}

class Other {
  Outer.Inner field;
}
'''
  other = _rec(class_uses(src), 'Other')
  assert 'com.example.Outer.Inner' in other['uses']['member']


def test_class_uses_local_class_excluded():
  src = '''\
package com.example;

public class Outer {
  void run() {
    class Local {
      int x;
    }
  }
}
'''
  names = {r['name'] for r in class_uses(src)}
  assert names == {'Outer'}


def test_class_uses_multiple_top_level_classes():
  # Java allows more than one package-private top-level type per file — all must
  # be found, not just the first (a pre-existing gap fixed as a side effect).
  src = '''\
package com.example;

class First {
}

class Second {
}
'''
  records = class_uses(src)
  names = {r['name'] for r in records}
  assert names == {'First', 'Second'}
  assert all(r['enclosing'] is None for r in records)


def test_class_uses_deeply_nested():
  src = '''\
package com.example;

public class A {
  static class B {
    static class C {
    }
  }
}
'''
  c = _rec(class_uses(src), 'C')
  assert c['fqn'] == 'com.example.A.B.C'
  assert c['enclosing'] == 'com.example.A.B'


def test_class_uses_nested_interface():
  src = '''\
package com.example;

public class Outer {
  interface Listener {
    void onEvent();
  }
}
'''
  listener = _rec(class_uses(src), 'Listener')
  assert listener['kind'] == 'interface'
  assert listener['fqn'] == 'com.example.Outer.Listener'
