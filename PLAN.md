# examui — development plan

Flask web app for oral exam assistance. Replaces the old `p2e` CLI + p2e-serve FastAPI
script. Run with `./run.sh` (binds to 127.0.0.1:8765; reach from tablet via SSH tunnel).

---

## Environment

`run.sh` sets relevant environment variables and calls `uv run flask run`.

Student javadoc: `STUDENT_BASE/<email>/javadoc/`
Student source:  `STUDENT_BASE/<email>/source/src/main/java/` 
Current note:    `EVAL_DIR/notes/<email>.md`
Marks:           `EVAL_DIR/marks.tsv`

---

## Package layout

```
examui/
  pyproject.toml      uv_build, src/ layout
  run.sh
  src/examui/
    __init__.py       create_app(), registers blueprints
    config.py         reads env vars, exposes Path constants
    models/
      history.py      all_students() → dict[email, Student]; module-level _cache
      oral.py         load_marks, notes, javadoc, source tree/file/symbols
    views/
      history.py      blueprint 'history'  prefix /history
      oral.py         blueprint 'oral'     prefix /oral
    templates/
      base.html       Bootstrap 5.3.3 + Bootstrap Icons, dark navbar
      history/
        list.html     DataTables 2.0.8 + jQuery, date filter, "Has ~" checkbox
        detail.html   per-event timeline with coloured badges
      oral/
        student.html  3-tab page: Note / Source / Javadoc
```

---

## Data model

### `ExamEvent` (history.py)
```python
date:      str   # YYMMDD
risultato: str   # "AS" | "RIx" | "REx" | "19V" | "19R" | …
note:      str | None
```

`risultato` is always `voto[:2].upper() + stato[:1]` from verbali XLS, or `"AS"` for
iscrizioni-only rows (absent). Exactly as the Snakemake `get_history` rule computes it.

Badge colours in `detail.html`:
- `AS`  → gray "Assente"
- `RI*` → orange "Ritirato"
- `RE*` → red "Respinto"
- ends `R` → blue `"<grade> ~"` (refused grade)
- ends `V` → green `"<grade>"` (accepted)

### `Student` (history.py)
```python
email, matricola, name: str
events: list[ExamEvent]   # descending by date
```

`all_students()` returns a module-level cached dict. Restart the server to refresh.

---

## Routes

| Method | URL | Description |
|---|---|---|
| GET | `/` | redirect → `/history/` |
| GET | `/history/` | student list (DataTables) |
| GET | `/history/<email>` | student timeline detail |
| GET | `/oral/<email>` | oral exam page (3 tabs) |
| POST | `/oral/<email>/note` | save note (form field `note`) |
| GET | `/oral/<email>/javadoc/` | serve javadoc root |
| GET | `/oral/<email>/javadoc/<path>` | serve javadoc file |
| GET | `/oral/<email>/source/tree` | JSON source file tree |
| GET | `/oral/<email>/source/file?path=` | JSON `{lines, symbols}` |
| GET | `/oral/pygments.css` | Pygments CSS for source highlighting |

---

## History list (`/history/`)

- DataTables 2.0.8 + jQuery 3.7.1 (jQuery required — CDN bundle references it)
- Date dropdown pre-selected to `EXAM_DATE`; custom `DataTable.ext.search` filter
- "Has ~" checkbox filters to students with at least one refused grade
- Columns: Name, Email (linked), Matricola, Results (#non-AS), First, Last, First eval
- `students_json` embedded in page as JS constant; `has_refused` boolean per student

## History detail (`/history/<email>`)

- Timeline of all events, newest first
- "Oral →" button appears **only on the event row matching `EXAM_DATE`** (sources exist
  only for the current exam date)
- `exam_date` is passed from the view but `in_exam` is no longer used

## Oral page (`/oral/<email>`)

Three Bootstrap tabs:

### Note tab
- Textarea (monospace), auto-saves on blur and after 2 s debounce
- `•` in tab label while dirty, `✓` (green) briefly after save

### Source tab
- Left panel (220 px): file tree loaded lazily on first tab open
- Right panel: toolbar + code area
  - Toolbar: filename, symbol search input, symbol select dropdown, Javadoc button,
    font-size select (11–16 px, persisted in localStorage as `oral-src-font-size`)
  - Code: per-line `<div id="src-L{n}">` with line-number gutter, javadoc icon gutter,
    then Pygments-highlighted code span
  - Book icon (`.src-jd`) in gutter on symbol lines; clicking navigates javadoc iframe
    to `ClassName.html#anchor` and switches to Javadoc tab
  - Symbol dropdown scrolls to `src-L{n}` via `scrollIntoView`

Pygments: `linenos=False`, `cssclass='src'`, `style='default'`
`_split_html_lines()` in `oral.py` splits highlighted HTML into per-line strings while
properly closing/reopening `<span>` tags at each newline boundary.

### Javadoc tab
- `<iframe>` pointing to `/oral/<email>/javadoc/`
- Disabled (greyed-out tab) when no javadoc directory exists

---

## Completed this session

- **tree-sitter symbol extraction** — `_symbols()` returns `{kind, name, line, anchor}`;
  `anchor = "methodName(Type1,Type2)"` for correct Javadoc deep-links; handles records.
  Parameter types are fully qualified using the file's `package` + `import` declarations
  (`scoped_identifier` child of `package_declaration` / `import_declaration` nodes);
  same-package types resolved as `package.SimpleName`.
- **Javadoc iframe fragment navigation** — `openJavadoc(url)` defers `frame.src` to
  `shown.bs.tab` event so fragment scroll works (hidden iframe has no viewport).
- **Empty note deletes file** — `save_note()` calls `p.unlink()` when cleaned text is empty.
- **Source tree trivial filter** — 3-way select (Relevant / All / Trivial) replaces checkbox.
  Trivial = files matching `*Exception.java`, `*Error.java`, `*Client.java`, `package-info.java`;
  directories matching `client` / `clients`. Empty dirs after filtering are pruned.
- **Dependency graph — richer edges + SCC layout + transitive reduction + SVG sizing**
  - `parsing.py`: `_walk_uses` extended with inherits, type bounds, local variables,
    `new` expressions; `class_uses` returns 4-tuple `(pkg, simple, uses, symbol_count)`.
  - `oral.py`: `_tarjan_sccs()` for topological ordering (foundations first);
    `_transitive_reduction()` removes edges covered by longer paths (condensation-based);
    edge direction reversed in Graphviz so foundations appear on the left (`rankdir=LR`);
    multi-node SCCs rendered as dashed cluster subgraphs.
  - `student.html`: SVG scaled to fit container via `viewBox`-based explicit pixel sizing.

---

## Pending / next session

### 2. Global symbol search

Index all file symbols at tree-load time, provide a search input that filters across
all files, click to open the file and scroll to the symbol.

### 2. Marks / test results on oral page header

Show relevant row from `marks.tsv` (score, test counts) in the oral page header area.

### 3. Unit tests for `parsing.py`

`parsing.py` has no Flask/config dependency and is directly testable. Worth adding
pytest tests covering at least:
- `symbols()`: classes, interfaces, records, methods, constructors, enums
- `class_uses()`: each dependency category (member, parameter, return, inherits, bound,
  local, instantiates); scoped type names; generics and arrays; self-loop filtering
- `_tarjan_sccs()` can be extracted or tested indirectly via known graphs

### 4. Future: UML / call graph

With tree-sitter in place, additional AST walks can extract:
- **UML class diagram**: fields (`field_declaration`), methods with signatures,
  superclass (`superclass`), interfaces (`super_interfaces`)
- **Call graph within file**: `method_invocation` nodes inside method bodies
- **Dependency graph**: `import_declaration` nodes + type references

Suggested rendering: Mermaid.js (CDN, no server side) for class diagrams;
D3 or Cytoscape.js for graphs. These would become additional sub-tabs or panels
in the Source tab.

---

## Dependencies (current)

```toml
dependencies = ["flask", "pandas", "xlrd", "pygments", "tree-sitter", "tree-sitter-java"]
```
