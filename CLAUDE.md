# examui — developer notes

## Purpose

Flask web application used during oral exams for PROGRAMMAZIONE II. It shows each student's exam history, lets the examiner take notes and record a provisional mark, and displays the student's submitted Java source code (with syntax highlighting, symbol navigation, dependency graph, and Javadoc).

## Configuration

All stable configuration lives in a TOML file pointed to by the `EXAMUI_CONFIG` env var (set in `.envrc`). Copy `config.toml.example` to `config.toml` and fill in your values:

```toml
[paths]
history_dir  = "/path/to/exams/history"
evals_dir    = "/path/to/exams/evals"
student_base = "/path/to/exams/students"
projects_dir = "/path/to/projects"

[exam]
slot_minutes     = 30
trivial_packages = ["client", "clients", "util", "utils"]
course_name      = "Programmazione II"
course_degree    = "Informatica"           # optional, for giustifica

[vscode]
tunnel = "santinivm"          # optional; enables the "Open in VSCode" button in the Source tab

[booking]
cal_url = "https://cal.com/username/event-name"   # optional; enables the public schedule page

[actions]
teacher_email  = "teacher@example.com"
teacher_name   = "Name Surname"
subject_prefix = "[CourseCode] "
email_domain   = "students.university.edu"
titoli         = ["lo studente", "la studentessa", "il dottore", "la dottoressa"]
```

`tomllib` (stdlib ≥ 3.11) is used to parse it — no extra dependency.

Two env vars are intentionally kept outside the TOML because they are ephemeral simulation overrides:

| Variable | Format   | Effect                                               |
|----------|----------|------------------------------------------------------|
| `TODAY`  | `YYMMDD` | Overrides the date used to select the active exam session |
| `NOW`    | `HHMM`   | Overrides the current time used by `/api/pace`       |

## Running

### Local development

```bash
source .envrc   # or: direnv allow
./bin/debug
```

Runs gunicorn with `--workers=1 --reload`. The `.envrc` must export `EXAMUI_CONFIG` pointing at a populated `config.toml`. `TODAY` defaults to today's date (`YYMMDD`); override to pin which day's oral slots are shown in the schedule view.

`NOW` (`HHMM`) overrides the current time used by `/api/pace`. Combined with `TODAY` this lets you simulate any point during the exam day without touching real data:

```bash
TODAY=260615 NOW=1145 ./bin/debug
```

### Remote access via SSH tunnel

`./bin/server` is the `command=` entry in `~/.ssh/authorized_keys` on the exam host:

```text
command="/path/to/bin/server",no-pty,no-agent-forwarding,no-X11-forwarding,permitopen="localhost:8765" ssh-ed25519 AAAA...
```

It sources `.envrc` from the project root, starts gunicorn on `127.0.0.1:8765`, and kills it when the SSH connection closes. Logs to `/tmp/examui.log`.

`./bin/client` runs on the tablet (Termux). It sources `.envrc` from the project root for:

| Variable | Meaning |
| -------- | ------- |
| `EXAMUI_HOST` | SSH host alias (from `~/.ssh/config`) |
| `EXAMUI_KEY` | Path to the dedicated SSH private key |
| `EXAMUI_PORT` | Local/remote port (default `8765`) |

It opens the tunnel, waits for the port to be reachable, launches the browser via `termux-open-url`, and tears down the tunnel on Ctrl-C.

Single-worker gunicorn is a hard requirement (in-process `@cache`).

### `bin/publish` — deploy the public schedule page

Fetches `GET /api/schedule/public` from the running local app, writes a `netlify.toml` (to suppress any build command), and deploys to the Netlify site via `netlify deploy --prod`. Reads `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` from `.envrc`. Requires `netlify-cli` installed on the server (`npm install -g netlify-cli`). The target site is `prog2unimi-esame.netlify.app`.

### `bin/giustifica` — CLI certificate generator

Generates a giustifica HTML file from the command line via `curl`:

```bash
./bin/giustifica <email-fragment> <titolo> [inizio] [fine]
```

Sources `.envrc` for `EXAMUI_PORT` (default `8765`). Accepts a partial email address — the server resolves it to a unique match; prints matching candidates and exits if ambiguous. Saves output as `giustifica-<fragment>.html` in the current directory. Uses `--connect-timeout 5` so a missing server fails immediately with a clear message.

---

## Data sources and what they mean

### `HISTORY_DIR/iscrizioni/*.xls`

One XLS per exam session, named `YYMMDD.xls` (the stem is the exam date used everywhere as a key). Each row is a student enrolled for that session. Columns: `Matricola`, `Email` (username only, no domain), `Cognome`, `Nome`.

- A student enrolled here but absent from verbali for that date → `ExamEvent(date, mark=None)`.
- The **most recent** XLS stem is `exam_date()` — the current/live exam.

### `HISTORY_DIR/verbali/*.xls`

Registrar verbali. Each row is a student who sat an exam and got a result. Columns include `Matricola`, `Voto` (grade), `Stato Esito` (outcome state), `Data appello` (date), `Descrizione insegnamento`. Only rows where `Descrizione insegnamento` matches `config.COURSE_NAME` (case-insensitive via `casefold()`) are used.

Mark encoding from verbali: handled by `Mark.from_verbale(voto, stato)`. `RE*` → `respinto`, `RI*` → `ritirato`, numeric voto + stato `V` → `passato`, numeric + other → `rifiutato`.

### `EVALS_DIR/<date>/marks.tsv`

TSV with one row per student who turned in source for the current exam. Pre-populated at exam start. Columns:

| Column | R/W | Meaning |
| ------ | --- | ------- |
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

### `STUDENT_BASE/<email>/computed/`

Optional directory of plain-text files produced during automated grading. Served read-only by the Details tab in `student.html` via `GET /api/<email>/computed/files` (file list) and `GET /api/<email>/computed/file?name=<filename>` (content). Not cached — files are small and read on demand.

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

#### `config.now()` — injectable current time

Returns `datetime.now()` unless the `NOW` env var (`HHMM`) is set, in which case it builds a datetime from `TODAY + NOW`. Used by `/api/pace` to allow time simulation during development.

#### `exam_date()` — `@cache`

Returns the stem of the most recent iscrizioni XLS (`YYMMDD`).

#### `load_project_htmls()` — `@cache`

Returns `list[tuple[stem, html_content]]` for all HTML files found at the first directory level inside `PROJECTS_DIR/<exam_date>.zip`. README comes first; the rest are sorted alphabetically. References to `polyfill.io` are rewritten to the Cloudflare equivalent (`cdnjs.cloudflare.com/polyfill/`) so browsers do not prompt for credentials. Warmed up at startup.

#### `all_students()` — `@cache`

Reads all iscrizioni XLS, all verbali XLS, past notes, and current marks.tsv once at startup. Builds the full `dict[email, Student]`. Students with source in marks.tsv get an `UnderEvaluationEvent` as their first event; enrolled-but-absent students get `ExamEvent(date, mark=None)` for the current date. No filesystem check for source presence.

---

## Java language analysis (`src/examui/lang/`)

No I/O, no Flask, no config dependency — importable standalone for unit tests.

### Tests

Tests live in `tests/lang/`. Run with:

```bash
uv run pytest tests/
```

`pytest` is in `[dependency-groups] dev` in `pyproject.toml` (no extra install needed with `uv`).

#### Known quirks (discovered while writing tests)

- **Primitive types not in `uses`**: `_collect_type_refs` only visits `type_identifier` nodes. Primitive types (`int`, `double`, etc.) are represented by `integral_type`/`floating_point_type` nodes in tree-sitter-java and are therefore invisible to `class_uses` — they never appear in any `uses` set. Use reference types in tests that need to assert on parameter/return/local uses.
- **Abstract class detection broken**: `child_by_field_name('modifiers')` returns `None` for `class_declaration` in the installed tree-sitter-java version, so `class_uses` always returns `kind='class'` even for `abstract class` declarations. The `'abstract'` kind is effectively dead code until this is fixed upstream or the parsing is reworked.

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

### `views/schedule.py` — `GET /schedule`, `GET /api/pace`, `GET /api/schedule/public`

All `UnderEvaluationEvent` students for the current exam. Includes full `Metrics` fields (via `dataclasses.asdict`) plus `summary_mark`, `current_mark` (from `live.mark.provisional`), and `matricola`. Sorted by `slot`. Each row also carries `is_current` and `is_next` booleans — `True` for the first and second unmarked students (non-empty `current_mark`) with a booked slot, used by `schedule.js` to render caret icons. Also computes `slot_dates` (sorted list of distinct `YYYY-MM-DD` strings from booked slots). Passes `rows`, `today` (ISO date string), `slot_dates`, and the `[actions]` config values to `schedule.html`.

`GET /api/pace` — returns schedule pace as JSON. Reads `provisional` live (not cached) for all slotted students. Only considers slots booked for **today**. Response: `{visible, delta}`. `visible` is `false` when no slots exist for today, when `now` is more than 60 minutes before the first slot, or when all today's students already have a provisional mark. `delta` = `(next_pending_slot − now)` in minutes; positive = ahead, negative = behind. Uses `config.now()` so `NOW` env override applies.

`GET /api/schedule/public` — renders `public_schedule.html`, a standalone page for students. Lists all `UnderEvaluationEvent` students sorted by matricola, showing their booked slot (formatted in Italian) and a pre-filled cal.com booking link (`config.CAL_URL?name=…&email=…&matricola=…`) for those without a slot. Bakes in the generation timestamp. Requires `[booking] cal_url` in config; booking links are omitted if absent.

### `views/teacher.py` — `GET /teacher`, `GET /api/teacher/file/<filename>`

Serves the exam instruction documents extracted from `PROJECTS_DIR/<exam_date>.zip`.

- `GET /teacher` — renders `teacher.html` with `files = load_project_htmls()`.
- `GET /api/teacher/file/<filename>` — returns the HTML content for the given stem (`filename` is the stem without `.html`). Content is served with `Content-Type: text/html; charset=utf-8`. Returns 404 if the stem is not in the loaded zip.

### `views/student.py` — per-student routes

- `GET /student/<email>` — renders `student.html`. Passes `email`, `name`, `matricola`, `events` (only `ExamEvent` instances — `UnderEvaluationEvent` is excluded), `current` (`UnderEvaluationEvent | None`), `slot_minutes`, `vscode_url` (`https://vscode.dev/tunnel/<tunnel><STUDENT_BASE>/<email>/source` when `[vscode] tunnel` is set and student is in current exam, else `None`).
- `POST /api/<email>/note` — saves `note` (long-form, to `.md` file). Form field: `note`.
- `POST /api/<email>/mark` — saves both `mark` and `annotation` to marks.tsv via `live.mark.save()`. Form fields: `mark`, `annotation`.
- `GET /student/<email>/giustifica` — renders a standalone `giustifica.html` certificate page ready for browser print-to-PDF. Query params: `titolo` (required), `inizio` and `fine` (`HH:MM`, optional — default to slot start and slot start + `SLOT_MINUTES`). The `<email>` segment accepts a partial match: if it uniquely identifies one current-exam student the request proceeds; if ambiguous, returns `{"error": "ambiguous", "matches": [...]}` with HTTP 400.
- `GET /api/<email>/computed/files` — returns sorted JSON list of filenames in `STUDENT_BASE/<email>/computed/`; empty list if directory absent. Only available for current-exam students.
- `GET /api/<email>/computed/file?name=<filename>` — returns raw text content of one computed file; path-traversal guarded. Only available for current-exam students.
- Source/Javadoc routes delegate to `source.*` functions.

---

## Templates

Templates live at `src/examui/templates/`. Static files live at `src/examui/static/`.

**Separation of concerns**: CSS and JavaScript must live in static files (`.css` / `.js`), not embedded in templates. The only inline `<script>` block permitted in a template is a `CFG = {...}` object that bakes in server-rendered values (URLs, config) needed by the companion `.js` file. Inline `<style>` blocks are never used. Inline `style=` attributes on individual elements are acceptable for one-off layout values that don't belong in a stylesheet.

### `base.html`

Bootstrap 5 + Bootstrap Icons CDN. Navigation bar (History / Schedule / Teacher buttons + Active timer button) is in the shared `base.html` header block — `#active-btn` is rendered here, JS activates it per-page. The Teacher button is shown only when `has_teacher` is true (injected via a context processor when `config.PROJECTS_DIR` is set).

Navbar also contains `#wall-clock` (current time, `HH:MM`, updated every second by `common.js`) and `#pace-badge` (ahead/behind indicator, polling `/api/pace` every 60 s). Both are visible on every page. `#pace-badge` is hidden when no slots are booked, when all students are done, or before the first slot's window has passed.

### `history.html`

DataTables. `CFG = {students: [...]}`. Filters: date dropdown, kind dropdown (All/Nuovo/Assente/Passato/Rifiutato/Ritirato/Respinto), page-length select, text search. Links to `/student/<email>`. Filter state in `sessionStorage['history-filters']`. Active-timer button handled by `common.js`.

### `schedule.html`

DataTables. `CFG = {rows, emailDomain, teacherEmail, teacherName, subjectPrefix, slotMinutes, titoli}`. Columns: checkbox, slot, name, matricola, mark, tests, javadoc, cyclic, SLOC, docs, files, client SLOC, client files. Date filter dropdown (populated from `slot_dates`; `▶` prefix on today's date; sentinel value `__unbooked__` for students with no slot) and "New only" checkbox filter. Links to `/student/<email>`. Active-timer button handled by `common.js`.

**Actions dropdown** — enabled when ≥ 1 row is checked:

- **Compose BCC email** — always available when ≥ 1 checked. Opens `mailto:?to=<teacher>&bcc=<students>&subject=<prefix>` in the system mail app. Student addresses are assembled as `<username>@<email_domain>`.
- **Giustifica** — enabled only when exactly 1 student with a booked slot is checked. Opens a modal to select `titolo` (from `CFG.titoli`) and review/edit `inizio`/`fine` times (pre-filled from the slot; a "Round to hour" button floors inizio and ceils fine). Confirming opens `/student/<email>/giustifica?...` in a new tab.
- **SIFA** — enabled when ≥ 1 checked. Downloads a CSV file (`sifa-YYYYMMDD-HHMM.csv`) with one line per selected student that has a provisional mark (rows without a mark are silently skipped). Format: `matricola,mark,DD/MM/YYYY` where the date is taken from the student's booked slot, falling back to `CFG.examDate` (today's ISO date).

`syncCheckboxes()` is the single function responsible for updating all checkbox states and enabling/disabling the dropdown and its items; it is called from both `drawCallback` and every individual checkbox/select-all interaction.

### `public_schedule.html`

Standalone (does not extend `base.html`). Bootstrap 5 CDN. Italian language. Intended for students — shows only matricola and slot, no names or marks. Sorted by matricola. Contains:

- Header: course name + "Appello del \<date\>" inline in lighter font.
- Yellow warning box (`alert-warning`) with three bullet points: booking instructions (with prefill note), slot-table currency notice (with generation timestamp), vademecum link.
- Counts row (Ammessi / Prenotati / Da prenotare) — placed *below* the table (teacher-facing info).
- Table: Matricola | Slot | action (green "Prenotato" badge or "Prenota →" button linking to prefilled cal.com URL).

### `teacher.html`

Extends `base.html`. Loads `teacher.css` and `teacher.js`. `{% block content %}` contains a full-height tabbed layout (one tab per HTML file from the zip, README first). Each tab pane holds an iframe pointing at `/api/teacher/file/<stem>`. Iframes are lazy-loaded: the first tab's iframe is loaded immediately by `teacher.js`; subsequent iframes load on first `shown.bs.tab` event.

### `giustifica.html`

Standalone (does not extend `base.html`). A4 portrait print layout via `@page { size: A4 portrait; margin: 2cm }`. Structure: university logo (`static/logo.jpg`), right-aligned date line (`Milano, DD/MM/YYYY`), body paragraph, right-aligned signature block (label + 2.5 cm gap for handwritten signature + teacher name), fixed footer with department address in a smaller font.

### `student.html`

Key pattern at top:

```jinja
{% set cm = current.mark.provisional if current else none %}
```

Single read of marks.tsv, reused for all conditional logic.

Tab visibility: History tab always visible (shows only `ExamEvent` instances — `UnderEvaluationEvent` is not listed there). Note/Source/Deps/Javadoc/Details tabs enabled when `current` is truthy (i.e. student is `UnderEvaluationEvent`), regardless of provisional mark value.

Source tab toolbar contains an "Open in VSCode" button (`bi-code-square`) when `vscode_url` is set and `current` is truthy — opens `https://vscode.dev/tunnel/<name><source-root>` in a new tab (workspace only; no file-open via URL).

Details tab: `<select id="details-select">` dropdown populated lazily on first tab open from `/api/<email>/computed/files`; selecting a filename fetches and displays its content in `<pre id="details-content">`.

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

Drives `#wall-clock` (ticks every second) and `#pace-badge` (polls `/api/pace` every 60 s). Badge shows `+Xm` (green) when ahead or `-Xm` (red) when behind. Visibility is controlled entirely by the server (`visible` field): the badge is hidden before the 60-minute pre-window, when no slots exist for today, and after the last student is marked. When the exam timer is running (`sessionStorage['examTimer']`), the client adds back the elapsed time since `startMs` to freeze the displayed delta at the value it had when the current student's exam started.

### `static/history.js`

DataTables for history list. Uses `renderMark(row.summary_mark, row.in_current ? '' : undefined)`. Filter state in `sessionStorage['history-filters']` — persists `date`, `kind`, `order`, `search`, `pageLen`. Kind filter options: `nuovo` (in current, no summary_mark), `assente` (no summary_mark), or match `summary_mark.kind`.

### `static/schedule.js`

DataTables for schedule. Uses `renderMark(row.summary_mark, row.current_mark)`. `iconFail(val)` / `iconCycles(val)` — Bootstrap Icons for tests/javadoc/cycles. Date filter: `#date-filter` select; value `__unbooked__` matches `row.slot === null`, any other non-empty value matches `row.slot.startsWith(date)`. "New only" filter: `row.summary_mark === null`. Active-timer button from `common.js`.

`createdRow` adds `table-warning` for the active-timer student. The name cell render prepends `bi-caret-right-fill text-primary` for `is_current` and `bi-caret-right text-secondary` for `is_next`; active-timer highlight takes priority over the caret icons.

**Selection and Actions**: `selectedEmails` (`Set`) tracks checked rows across redraws. `syncCheckboxes()` is the single point of truth — called from `drawCallback` and all checkbox interactions (individual row and select-all header). It syncs checkbox DOM state, enables/disables the Actions dropdown button (`#actions-btn`, enabled when ≥ 1 selected), enables/disables `#giustifica-action` (only when exactly 1 student with a `slot` is selected), and enables/disables `#sifa-action` (when ≥ 1 selected).

### `static/student.js`

- **Timer**: `sessionStorage['examTimer'] = {email, startMs, slotMs}`. Progress bar at 80/90/95%. Slot duration editable via `#slot-input`.
- **Note save**: `POST /api/<email>/note` with `note` field only (long-form). Debounced 2 s + blur. Status shown in `#tab-note-status` (in the tab label).
- **Mark save**: `POST /api/<email>/mark` with `mark` + `annotation` fields together (blur/Enter on either input triggers save).
- **Source tree, symbol search, file viewer, deps graph, Javadoc**: fetch from `/api/<email>/source/*` and `/api/<email>/javadoc/`. Source tree loaded lazily on first Source tab open. Panzoom (CDN) used for the deps SVG; double-click resets zoom.
- **Font size**: `localStorage['oral-src-font-size']` key; select `#src-fontsize`.
- **Details tab**: file list fetched lazily on first `shown.bs.tab` from `/api/<email>/computed/files`; content fetched on `#details-select` change from `/api/<email>/computed/file?name=…`.

---

## Caching philosophy

- `@cache` used consistently throughout — never `@lru_cache` with explicit size.
- `all_students()`, `exam_date()`, `load_project_htmls()`: cached for process lifetime.
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
