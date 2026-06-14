# examui — developer notes

## Purpose

Flask web application used during oral exams for PROGRAMMAZIONE II. It shows each student's exam history, lets the examiner take notes and record a provisional mark, and displays the student's submitted Java source code (with syntax highlighting, symbol navigation, dependency graph, and Javadoc).

## Running

### Local development

```bash
source .envrc   # or: direnv allow
./bin/debug
```

Runs gunicorn with `--workers=1 --reload`. Expects `HISTORY_DIR`, `EVALS_DIR`, `STUDENT_BASE` in the environment (see `.envrc.example`). `SLOT_MINUTES` defaults to 30. `TODAY` defaults to today's date (`YYMMDD`); override to pin which day's oral slots are shown in the schedule view.

### Remote access via SSH tunnel

`./bin/server` is the `command=` entry in `~/.ssh/authorized_keys` on the exam host:

```
command="/path/to/bin/server",no-pty,no-agent-forwarding,no-X11-forwarding,permitopen="localhost:8765" ssh-ed25519 AAAA...
```

It sources `.envrc` from the project root, starts gunicorn on `127.0.0.1:8765`, and kills it when the SSH connection closes. Logs to `/tmp/examui.log`.

`./bin/client` runs on the tablet (Termux). It sources `.envrc` from the project root for:

| Variable | Meaning |
|----------|---------|
| `EXAMUI_HOST` | SSH host alias (from `~/.ssh/config`) |
| `EXAMUI_KEY`  | Path to the dedicated SSH private key |
| `EXAMUI_PORT` | Local/remote port (default `8765`) |

It opens the tunnel, waits for the port to be reachable, launches the browser via `termux-open-url`, and tears down the tunnel on Ctrl-C.

Single-worker gunicorn is a hard requirement (in-process `@cache`).

---

## Data sources and what they mean

### `HISTORY_DIR/iscrizioni/*.xls`

One XLS per exam session, named `YYMMDD.xls` (the stem is the exam date used everywhere as a key). Each row is a student enrolled for that session. Columns: `Matricola`, `Email` (username only, no domain), `Cognome`, `Nome`.

- A student enrolled here but absent from verbali for that date → `ExamEvent(date, mark=None)`.
- The **most recent** XLS stem is `exam_date()` — the current/live exam.

### `HISTORY_DIR/verbali/*.xls`

Registrar verbali. Each row is a student who sat an exam and got a result. Columns include `Matricola`, `Voto` (grade), `Stato Esito` (outcome state), `Data appello` (date), `Descrizione insegnamento`. Only rows where `Descrizione insegnamento == 'PROGRAMMAZIONE II'` are used.

Mark encoding from verbali: handled by `Mark.from_verbale(voto, stato)`. `RE*` → `respinto`, `RI*` → `ritirato`, numeric voto + stato `V` → `passato`, numeric + other → `rifiutato`.

### `EVALS_DIR/<date>/marks.tsv`

TSV with one row per student who turned in source for the current exam. Pre-populated at exam start. Columns:

| Column | R/W | Meaning |
|--------|-----|---------|
| `mark` | R/W | Provisional vote (`AS`, `RE`, numeric) |
| `note` | R/W | Short pre-exam comment |
| `email` | R/O | Email username |
| `regnum` | R/O | Matricola |
| `tests` | R/O | `SUCCESS`/`FAILURE` |
| `javadoc` | R/O | `SUCCESS`/`FAILURE` |
| `cyclic` | R/O | `YES`/`NO` |
| `code` | R/O | Source lines of code (clients excluded) |
| `docs` | R/O | Documentation lines (clients excluded) |
| `file` | R/O | File count (clients excluded) |
| `ccode` | R/O | Source lines of code (clients only) |
| `cfile` | R/O | File count (clients only) |
| `date` | R/O | Booked oral slot (`YYMMDD-HHMM`) |
| `upload` | R/O | Submission timestamp (`YYMMDD-HHMM`) |
| `rej`/`acc`/`other` | R/O | Ignored by the UI |

**Source presence is determined by marks.tsv, not the filesystem.** If a student's email appears in marks.tsv, they get an `UnderEvaluationEvent` as their first event. If enrolled (in iscrizioni) but absent from marks.tsv, they get `ExamEvent(date, mark=None)` for the current date. No filesystem check is needed.

- Missing file → all enrolled students treated as absent for the current date (exam not yet prepared).
- Only `mark` and `note` columns are ever modified by the UI; all other columns are read-only.

### `EVALS_DIR/<date>/notes/<email>.md`

Long-form examiner notes for a student at a given exam date. Written live by the UI. Lines starting with `#` are stripped on save. Created/deleted as needed.

Past exam notes are read once at startup (baked into `Mark.note` on each `ExamEvent`). Current exam long notes are read/written live via `UnderEvaluationMark.note`.

### `STUDENT_BASE/<email>/source/`

Student's submitted Java project. Layout:
- If `source/src/main/java/` exists → that is the source root (Maven layout).
- Otherwise `source/` itself is the source root.

### `STUDENT_BASE/<email>/javadoc/`

Pre-built Javadoc HTML tree, served as static files by the `/api/<email>/javadoc/` route.

---

## Data model

Split across three modules:

### `src/examui/models/events.py` — pure frozen data classes (no I/O)

#### `Mark`

```python
@dataclass(frozen=True)
class Mark:
    kind: Literal['respinto', 'ritirato', 'passato', 'rifiutato']
    value: int | None = None   # numeric grade (passato/rifiutato only)
    note:  str | None = None   # long-form oral note from that session
```

`Mark.from_verbale(voto, stato)` classmethod builds a `Mark` from raw verbale columns: `RE*` → `respinto`, `RI*` → `ritirato`, numeric + `V` → `passato`, numeric + other → `rifiutato`.

#### `ExamEvent`

```python
@dataclass(frozen=True)
class ExamEvent:
    date: str        # 'YYMMDD'
    mark: Mark | None  # None = absent (enrolled but no verbale entry)
```

#### `Metrics` — read-only snapshot of marks.tsv static fields

```python
@dataclass(frozen=True)
class Metrics:
    tests_fail:   bool           # True = FAILURE
    javadoc_fail: bool           # True = FAILURE
    has_cycles:   bool           # True = cycles present
    main_sloc:    int            # source lines of code, clients excluded
    main_docs:    int            # documentation lines, clients excluded
    main_files:   int            # file count, clients excluded
    client_sloc:  int            # source lines of code, clients only
    client_files: int            # file count, clients only
    slot:         datetime | None  # booked oral slot
    upload:       datetime | None  # submission timestamp
```

Built once at `all_students()` time via `Metrics.from_row(row)`. Immutable for the process lifetime. `from_row` maps the raw TSV column names (`code`, `docs`, `file`, `ccode`, `cfile`, `tests`, `javadoc`, `cyclic`, `date`, `upload`) to the descriptive field names above, parsing booleans and datetimes.

#### `Student` — frozen dataclass

```python
@dataclass(frozen=True)
class Student:
    email: str; matricola: str; name: str
    events: list[ExamEvent | UnderEvaluationEvent]   # most-recent-first
```

There is no separate `current` field. A student is in the current exam when `events[0]` is an `UnderEvaluationEvent`. `current is None` from the old model is replaced by checking `isinstance(s.events[0], UnderEvaluationEvent)`.

`Student.summary_mark` property — returns `Mark | None`:
- First `passato` mark if one exists.
- First `rifiutato` mark if no `passato`.
- First `respinto`/`ritirato` mark otherwise.
- `None` — no notable history.

Additional read-only properties:
- `attempts` — count of events that have a mark (verbale present) or are `UnderEvaluationEvent`.
- `first` / `last` — date string of the first / most recent event.
- `first_attempt` — date of the first event that has a mark (or `UnderEvaluationEvent`).

`events` is most-recent-first. Do not use `reversed()` when you want the most recent entry.

### `src/examui/models/store.py` — all I/O

#### `UnderEvaluationMark` — live read/write proxy for one student's marks.tsv row

Private path/IO helpers (all instance methods):
- `_marks_path()` / `_note_path()` — compute the relevant file paths.
- `_read_tsv(field)` / `_write_tsv(**kwargs)` — read/write marks.tsv columns.
- `_read_md()` / `_write_md(text)` — read/write the `.md` long-note file.

R/W live properties:
- `provisional` — reads/writes marks.tsv `mark` column.
- `annotation` — reads/writes marks.tsv `note` column.
- `note` — reads/writes the `.md` file in the notes directory.

`save(provisional, annotation)` — writes both `mark` and `note` TSV columns in one operation.

`_write_tsv` reads and rewrites the whole file in one operation; accepts arbitrary column keyword arguments.

#### `UnderEvaluationEvent` — enrolled this exam, present in marks.tsv

Has `date: str`, `metrics: Metrics` (frozen, from marks.tsv row at build time), and `mark: UnderEvaluationMark` (live I/O proxy). Inserted as `events[0]` in `Student.events` for current-exam students with source.

#### `exam_date()` — `@cache`

Returns the stem of the most recent iscrizioni XLS (`YYMMDD`).

#### `all_students()` — `@cache`

Reads all iscrizioni XLS, all verbali XLS, past notes, and current marks.tsv once at startup. Builds the full `dict[email, Student]`. Students with source in marks.tsv get an `UnderEvaluationEvent` as their first event; enrolled-but-absent students get `ExamEvent(date, mark=None)` for the current date. No filesystem check for source presence.

---

## Java language analysis (`src/examui/lang/`)

No I/O, no Flask, no config dependency — importable standalone for unit tests.

### `lang/parsing.py`

Uses `tree-sitter` (via `tree_sitter_java`). Public API:

- `symbols(text)` → `list[dict]` — symbol list for the source navigator. Each entry: `{kind, name, line, anchor}`. `anchor` is `'name(FQN1,FQN2)'` for methods/constructors, `''` for type declarations.
- `class_uses(text)` → `(package, simple_name, uses, sym_count, kind)` — dependency information. `uses` is `{'member': set[FQN], 'parameter': set[FQN], 'return': set[FQN], 'inherits': set[FQN], 'bound': set[FQN], 'local': set[FQN], 'instantiates': set[FQN]}`. `kind` is one of `'class'`, `'abstract'`, `'interface'`, `'enum'`, `'record'`.

### `lang/graph.py`

Pure graph algorithms and Java class triviality classification. Public API:

- `is_trivial_package(rel_parts, trivial_packages)` — true if the package path matches any entry in `trivial_packages`.
- `is_trivial(stem, uses)` — true if the class name ends with `Exception`/`Error`/`Client`, or directly inherits from a throwable.
- `close_trivial(parsed)` — propagates triviality transitively through inheritance chains (mutates in place).
- `tarjan_sccs(nodes, adj)` → `list[list[str]]` — Tarjan's SCC algorithm; returns SCCs in topological order (foundations first).
- `transitive_reduction(nodes, adj, sccs)` → `dict[str, list[str]]` — removes inter-SCC edges made redundant by transitivity; intra-SCC edges are kept as-is.

## Source analysis (`src/examui/models/source.py`)

Filesystem I/O layer for student source code and Javadoc. Orchestrates `lang.parsing` and `lang.graph`; applies Pygments highlighting and Graphviz rendering. All public functions are `@cache`-decorated — computed once per process, warmed up at startup for all `UnderEvaluationEvent` students.

- `tree(email)` — directory tree as JSON-serialisable list.
- `all_symbols(email)` — flat list of all symbol dicts across non-trivial files.
- `file(email, relpath)` — Pygments-highlighted lines + symbols for one file.
- `deps(email)` — dependency graph `{'svg': ..., 'paths': {node_id: relpath}}`. Uses Tarjan SCC + transitive reduction + Graphviz.
- `javadoc_root(email)` — path to the pre-built Javadoc tree.
- `javadoc_path_for_source(relpath)` — maps a `.java` source relpath to the corresponding `.html` Javadoc path (`None` if not applicable).
- `pygments_css()` — returns the Pygments CSS string for the `src` class.
- `warmup(email)` — eagerly populates `tree`, `all_symbols`, and `deps` caches. Called at startup. (`file` is not pre-warmed — loaded on demand.)

"Trivial" files are excluded from the symbol index and dependency graph. Triviality is determined by:
1. Class/file name ends with `Exception`, `Error`, or `Client`.
2. Superclass (transitively) is trivial.
3. The file is in a package listed in `config.TRIVIAL_PACKAGES` (default: `client`, `clients`, `util`, `utils`).

Trivial propagation is transitive: if a superclass is trivial, all subclasses are also trivial.

---

## Views

### `views/history.py` — `GET /history`

All students enrolled at least once (past or current exam). Only `summary_mark` in the mark column — no provisional marks. Passes `students`, `exam_dates` (past dates only), `current_date` to `history.html`.

Each entry in `students` includes: `email`, `name`, `matricola`, `attempts`, `first`, `last`, `first_attempt`, `in_current` (bool), `dates` (list), `summary_mark` (`dataclasses.asdict(Mark)` or `None`).

### `views/schedule.py` — `GET /schedule`

All `UnderEvaluationEvent` students for the current exam. Includes full `Metrics` fields (via `dataclasses.asdict`) plus `summary_mark` and `current_mark` (from `live.mark.provisional`). Sorted by `slot`. Passes `rows`, `today` (ISO date string) to `schedule.html`.

### `views/student.py` — per-student routes

- `GET /student/<email>` — renders `student.html`. Passes `email`, `name`, `matricola`, `events` (only `ExamEvent` instances — `UnderEvaluationEvent` is excluded), `current` (`UnderEvaluationEvent | None`), `slot_minutes`.
- `POST /api/<email>/note` — saves `note` (long-form, to `.md` file). Form field: `note`.
- `POST /api/<email>/mark` — saves both `mark` and `annotation` to marks.tsv via `live.mark.save()`. Form fields: `mark`, `annotation`.
- Source/Javadoc routes delegate to `source.*` functions.

---

## Templates

Templates live at `src/examui/templates/`. Static files live at `src/examui/static/`.

### `base.html`
Bootstrap 5 + Bootstrap Icons CDN. Navigation bar (History / Schedule buttons + Active timer button) is in the shared `base.html` header block — `#active-btn` is rendered here, JS activates it per-page.

### `history.html`
DataTables. `CFG = {students: [...]}`. Filters: date dropdown, kind dropdown (All/Nuovo/Assente/Passato/Rifiutato/Ritirato/Respinto), page-length select, text search. Links to `/student/<email>`. Filter state in `sessionStorage['history-filters']`. Active-timer button handled by `common.js`.

### `schedule.html`
DataTables. `CFG = {rows: [...], today: 'YYYY-MM-DD'}`. Columns: slot, name, mark, tests, javadoc, cyclic, SLOC, docs, files, client SLOC, client files. "Today only" and "New only" checkbox filters. Links to `/student/<email>`. Active-timer button handled by `common.js`.

### `student.html`

Key pattern at top:
```jinja
{% set cm = current.mark.provisional if current else none %}
```
Single read of marks.tsv, reused for all conditional logic.

Tab visibility: History tab always visible (shows only `ExamEvent` instances — `UnderEvaluationEvent` is not listed there). Note/Source/Deps/Javadoc tabs enabled when `current` is truthy (i.e. student is `UnderEvaluationEvent`), regardless of provisional mark value.

Notes tab layout (top to bottom):
1. Label "Mark" + `mark-input` text field
2. Label "Note" + `annotation-input` text field
3. `note-editor` textarea (long-form notes, no label)

Status indicator is `#tab-note-status` (in the tab label itself), not a separate `#note-status` span.

---

## JavaScript

### `static/common.js`
Shared across all pages. Defines `renderMark(vm, cm)`:
- If `cm` is provided and non-empty (schedule context) → yellow provisional badge.
- If `vm` is set → verbali_mark badge using `MARK_CSS`/`MARK_LABEL` maps (kind → CSS class / short label).
- If `cm` is provided but empty (in schedule, no provisional) → empty info badge.
- Otherwise → empty string.

Also activates `#active-btn` (defined in `base.html`) for all pages using `sessionStorage['examTimer']`.

### `static/history.js`
DataTables for history list. Uses `renderMark(row.summary_mark, row.in_current ? '' : undefined)`. Filter state in `sessionStorage['history-filters']` — persists `date`, `kind`, `order`, `search`, `pageLen`. Kind filter options: `nuovo` (in current, no summary_mark), `assente` (no summary_mark), or match `summary_mark.kind`.

### `static/schedule.js`
DataTables for schedule. Uses `renderMark(row.summary_mark, row.current_mark)`. `iconFail(val)` / `iconCycles(val)` — Bootstrap Icons for tests/javadoc/cycles. "Today only" filter: `row.slot && row.slot.startsWith(CFG.today)`. "New only" filter: `row.summary_mark === null`. Active-timer button from `common.js`.

### `static/student.js`
- **Timer**: `sessionStorage['examTimer'] = {email, startMs, slotMs}`. Progress bar at 80/90/95%. Slot duration editable via `#slot-input`.
- **Note save**: `POST /api/<email>/note` with `note` field only (long-form). Debounced 2 s + blur. Status shown in `#tab-note-status` (in the tab label).
- **Mark save**: `POST /api/<email>/mark` with `mark` + `annotation` fields together (blur/Enter on either input triggers save).
- **Source tree, symbol search, file viewer, deps graph, Javadoc**: fetch from `/api/<email>/source/*` and `/api/<email>/javadoc/`. Source tree loaded lazily on first Source tab open. Panzoom (CDN) used for the deps SVG; double-click resets zoom.
- **Font size**: `localStorage['oral-src-font-size']` key; select `#src-fontsize`.

---

## Caching philosophy

- `@cache` used consistently throughout — never `@lru_cache` with explicit size.
- `all_students()`, `exam_date()`: cached for process lifetime.
- `tree`, `all_symbols`, `file`, `deps` in `models/source.py`: cached per email (or email+relpath).
- Live I/O (`provisional`, `annotation`, `note` on `UnderEvaluationMark`) intentionally **not** cached.
- Single-worker gunicorn is a hard requirement.

---

## Mark conventions

Verbale marks are represented by the `Mark` dataclass with a `kind` field:

| `kind`      | Meaning                                      |
|-------------|----------------------------------------------|
| `passato`   | Passed (numeric `value`, verbale stato `V`)  |
| `rifiutato` | Refused by student (numeric `value`, tilde)  |
| `respinto`  | Rejected/failed (`value` is `None`)          |
| `ritirato`  | Withdrawn (`value` is `None`)                |

`ExamEvent.mark is None` means the student was absent (enrolled but no verbale entry).

Provisional marks in marks.tsv (`UnderEvaluationMark.provisional`) are free-form strings entered by the examiner (e.g. `18`, `RE`, `RI`). They are not `Mark` objects.

`Student.summary_mark` returns the most notable `Mark` from past verbale events: first `passato` if any, then first `rifiutato`, then first `respinto`/`ritirato`, else `None`.

`renderMark(vm, cm)` in `common.js`: `vm` is `dataclasses.asdict(summary_mark)` (with `kind` and `value` keys) or `null`; `cm` is the provisional string or `undefined` (history context).
