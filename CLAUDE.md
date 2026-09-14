# examui — developer notes

## Purpose

Flask web application used during oral exams for PROGRAMMAZIONE II. It shows each student's exam history, lets the examiner take notes and record a provisional mark, and displays the student's submitted Java source code (with syntax highlighting, symbol navigation, dependency graph, and Javadoc).

## Configuration

All stable configuration lives in a TOML file pointed to by the `EXAMUI_CONFIG` env var (set in `.env`). Copy `config.toml.example` to `config.toml` and fill in your values:

```toml
[paths]
history_dir  = "/path/to/exams/history"
evals_dir    = "/path/to/exams/evals"
work_dir     = "/path/to/work/dir"               # ephemeral directory for pipeline artifacts
backup_dir   = "/path/to/exams/backup"           # archived raw submissions from past sessions (for the diff tool)

[exam]
slot_minutes     = 30
trivial_packages = ["client", "clients", "util", "utils"]  # optional, default shown
course_name      = "Programmazione II"
course_degree    = "Informatica"
teacher_email    = "teacher@example.com"
teacher_name     = "Name Surname"
subject_prefix   = "[CourseCode] "
email_domain     = "students.university.edu"
titoli           = ["lo studente", "la studentessa", "il dottore", "la dottoressa"]  # optional, default shown

[vscode]
tunnel = "santinivm"          # enables the "Open in VSCode" button in the Source tab

[booking]
cal_url  = "https://cal.com/username/event-name"   # enables the public schedule page
endpoint = "https://api.cal.com/v2/bookings"       # cal.com API endpoint
version  = "2024-08-13"                            # cal.com API version
event    = 1234567                                 # cal.com event type ID

[uploads]
url      = "https://api.upload.di.unimi.it/admin"
username = "teacher@university.edu"
session  = 1234                              # upload session ID (changes per semester)
```

`tomllib` (stdlib ≥ 3.11) is used to parse it — no extra dependency.

Every key shown above is mandatory except `trivial_packages` and `titoli`, which fall back to the defaults shown if omitted. `config.py`'s `_get(section, key, default_value)` helper enforces this: missing keys/sections raise `ConfigError` with a message naming the section, key, and config file path (instead of a bare `KeyError`), so misconfiguration fails loudly at import time rather than surfacing later as an `AttributeError` deep in a view. This applies even to fields used by optional UI features (e.g. `vscode.tunnel`, `booking.cal_url`) — every `examui` deployment must fill in the whole file, including pipeline-only sections (`uploads`, the pipeline-specific `booking` keys), regardless of whether the pipeline CLI is actually used.

Two paths are derived by convention rather than configured: `STUDENT_BASE` is always `work_dir/student`, and `PROJECTS_DIR` is always `history_dir/projects`. Neither has a TOML key — `config.py` builds them from `paths.work_dir` and `paths.history_dir` respectively.

`backup_dir` is unrelated to `history_dir`/`work_dir`/`PROJECTS_DIR`: it points at manually-maintained archives of *raw* past-session uploads (one `<YYMMDD>.zip` per exam date, each containing every student's numbered `<email>@domain/NNN-consegna.zip` resubmissions, as originally received — not the single latest-per-student copy the pipeline keeps in `work_dir/uploaded`). It is read by the Flask app's diff feature (see `views/student.py`, `models/diff.py`) — the pipeline CLI never touches it.

Two env vars are intentionally kept outside the TOML because they are ephemeral simulation overrides:

| Variable | Format   | Effect                                                    |
|----------|----------|-----------------------------------------------------------|
| `TODAY`  | `YYMMDD` | Overrides the date used to select the active exam session |
| `NOW`    | `HHMM`   | Overrides the current time used by `/api/pace`            |

Pipeline-only env vars (secrets, not in TOML):

| Variable           | Used by              | Meaning                                       |
|--------------------|----------------------|-----------------------------------------------|
| `UPLOADS_PASSWORD` | `fetch-uploads`      | Password for the uploads API                  |
| `CALCOM_KEY`       | `fetch-calendar`     | cal.com API bearer token                      |

## Running

### Local development

```bash
source .env   # or: direnv allow
./bin/debug
```

Runs gunicorn with `--workers=1 --reload`. `.env` must export `EXAMUI_CONFIG` pointing at a populated `config.toml`. `TODAY` defaults to today's date (`YYMMDD`); override to pin which day's oral slots are shown in the schedule view.

`NOW` (`HHMM`) overrides the current time used by `/api/pace`. Combined with `TODAY` this lets you simulate any point during the exam day without touching real data:

```bash
TODAY=260615 NOW=1145 ./bin/debug
```

### Remote access via SSH tunnel

`./bin/server` is the `command=` entry in `~/.ssh/authorized_keys` on the exam host:

```text
command="/path/to/bin/server",no-pty,no-agent-forwarding,no-X11-forwarding,permitopen="localhost:8765" ssh-ed25519 AAAA...
```

It sources `.env` from the project root, starts gunicorn on `127.0.0.1:8765`, and kills it when the SSH connection closes. Logs to `/tmp/examui.log`.

`./bin/client` runs on the tablet (Termux). It sources `.env` from the project root for:

| Variable | Meaning |
| -------- | ------- |
| `EXAMUI_HOST` | SSH host alias (from `~/.ssh/config`) |
| `EXAMUI_KEY` | Path to the dedicated SSH private key |
| `EXAMUI_PORT` | Local/remote port (default `8765`) |

It opens the tunnel, waits for the port to be reachable, launches the browser via `termux-open-url`, and tears down the tunnel on Ctrl-C.

Single-worker gunicorn is a hard requirement (in-process `@cache`).

### `bin/publish` — deploy the public schedule page

Starts a throwaway gunicorn instance on port `8766` (separate from the tunnel server on `8765`, single-worker as required) so the published page reflects the latest data regardless of whether the tunnel server is running or stale. Polls `/api/schedule/public` until the warmed-up app responds (up to 60s; `create_app()` warmup runs synchronously before gunicorn binds, so a response means the app is fully ready), fetches the page, kills the temporary server, writes a `netlify.toml` (to suppress any build command), and deploys to the Netlify site via `netlify deploy --prod`. Reads `NETLIFY_SITE_ID` from `.env`; `NETLIFY_AUTH_TOKEN` must be exported in the environment (`~/.bash_secrets` is sourced when present, so it also works from non-login shells). Requires `netlify-cli` on the server. The target site is `prog2unimi-esame.netlify.app`.

### `bin/giustifica` — CLI certificate generator

Generates a giustifica HTML file from the command line via `curl`:

```bash
./bin/giustifica <email-fragment> <titolo> [inizio] [fine]
```

Sources `.env` for `EXAMUI_PORT` (default `8765`). Accepts a partial email address — the server resolves it to a unique match; prints matching candidates and exits if ambiguous. Saves output as `giustifica-<fragment>.html` in the current directory. Uses `--connect-timeout 5` so a missing server fails immediately with a clear message.

### `bin/moss` — submit sources to MOSS for plagiarism detection

Standalone Python script (not part of the `examui` package), shebang `#!/usr/bin/env -S uv run python3` so it always runs with the project's dependencies regardless of CWD or shell activation, matching the `uv run`-based pattern of the other `bin/` scripts:

```bash
./bin/moss <students_dir> [--exclude DIR ...] [--filter REGEX] [--dry-run]
```

Requires `MOSS_USERID` env var — a personal MOSS account secret, unrelated to the `exam-pipeline` CLI, set in `.env` alongside the other secrets. Unlike the bash `bin/` scripts, `bin/moss` does not `source .env` itself, so the variable must already be in the shell's environment (e.g. via `direnv allow`, which loads `.env` automatically). Walks `<students_dir>/<student>/source/src/main/java`, skips empty files and top-level package dirs in `--exclude` (default `clients util`), uploads via `mosspy` with a `rich` progress bar, and prints the MOSS results URL. `--filter` restricts which students are processed (regex matched against the student dir name via `re.search`). `--dry-run` collects and counts files without submitting.

### `bin/clean` — remove Python/tooling cache clutter

```bash
./bin/clean
```

Removes `__pycache__`, `*.pyc`, `.pytest_cache`, and `.ruff_cache` anywhere under the project root (skipping `.venv`). `PYTHONDONTWRITEBYTECODE=1` is set in `.env` to stop `__pycache__` from being written in the first place; this script is for whatever predates that setting or slips through (e.g. tools that ignore the env var).

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

**Operational constraint:** `marks.tsv` is only read for the current exam date (`exam_date()`). Once a newer iscrizioni XLS is added, past `evals/<date>/marks.tsv` data (provisional marks, metrics) becomes invisible in the UI. Past notes files still pull their date into the student's history, but without a corresponding verbale entry the event renders as absent (mark=None) and the note content is not attached. Download verbali for a past exam **before** creating the next exam's iscrizioni to avoid this gap. Once the verbale is in place, notes reattach correctly.

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

`.github/workflows/tests.yml` runs this same command, plus `--cov=src/examui --cov-report=term-missing` (via `pytest-cov`, also in `[dependency-groups] dev`), on every push to `master` and on every pull request, using `astral-sh/setup-uv`. The suite is pure Python — no gradle/graphviz/JDK — so no extra setup steps are needed in CI. Coverage is reported for reference only — there is no enforced threshold, since only `lang/` and `data/` have tests; `views/`, `models/store.py`, `source.py`, and `pipeline/` are untested and always show 0%. The `term-missing` output is teed to `pytest-coverage.txt`, fed to `MishaKav/pytest-coverage-comment` (`hide-comment: true`, so it neither posts a PR comment nor a push commit-comment — its `coverageHtml` output is all that's used; `default-branch: master`, since the action's own default of `main` would otherwise point every per-file link at a nonexistent branch on this repo) to render it as a proper HTML table with a coverage-percentage badge and per-file links, which a final `if: always()` step appends to `$GITHUB_STEP_SUMMARY` — so it renders on the run's Summary page instead of the ASCII table being buried inside the pytest step's raw log.

#### Known quirks (discovered while writing tests)

- **Primitive types not in `uses`**: `_collect_type_refs` only visits `type_identifier` nodes. Primitive types (`int`, `double`, etc.) are represented by `integral_type`/`floating_point_type` nodes in tree-sitter-java and are therefore invisible to `class_uses` — they never appear in any `uses` set. Use reference types in tests that need to assert on parameter/return/local uses.
- **Abstract class detection broken**: `child_by_field_name('modifiers')` returns `None` for `class_declaration` in the installed tree-sitter-java version, so `class_uses` always returns `kind='class'` even for `abstract class` declarations. The `'abstract'` kind is effectively dead code until this is fixed upstream or the parsing is reworked.
- **Static access detection via uppercase heuristic**: `_walk_uses` detects static method calls (`UtilityClass.method()`) and static field access (`Constants.FIELD`) by checking if a `method_invocation`/`field_access` node's object is a plain `identifier` starting with uppercase. These are added to the `local` uses set. The heuristic relies on the Java naming convention (PascalCase for classes, camelCase for variables) and is reliable for idiomatic code. Without this, utility classes with only static methods would be invisible in the dependency graph.

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
- `highlight_lines(text)` — syntax-highlighted per-line HTML fragments for arbitrary Java source text (not tied to a student/`STUDENT_BASE`). `file()` uses it for the normal single-file view; `models/diff.py` reuses it for the diff view's two side-by-side columns, so both look identical stylistically.
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

All `UnderEvaluationEvent` students for the current exam. Includes full `Metrics` fields (via `dataclasses.asdict`) plus `summary_mark`, `current_mark` (from `live.mark.provisional`), and `matricola`. Sorted by `slot`. Each row also carries `is_current` and `is_next` booleans — `True` for the first and second unmarked students (non-empty `current_mark`) with a booked slot, used by `schedule.js` to render caret icons. Also computes `slot_dates` (sorted list of distinct `YYYY-MM-DD` strings from booked slots). Passes `rows`, `today` (ISO date string), `slot_dates`, and the teacher/email config values (`TEACHER_EMAIL`, `TEACHER_NAME`, `SUBJECT_PREFIX`, `EMAIL_DOMAIN`, `TITOLI`) to `schedule.html`.

`GET /api/pace` — returns schedule pace as JSON. Reads `provisional` live (not cached) for all slotted students. Only considers slots booked for **today**. Response: `{visible, delta}`. `visible` is `false` when no slots exist for today, when `now` is more than 60 minutes before the first slot, or when all today's students already have a provisional mark. `delta` = `(next_pending_slot − now)` in minutes; positive = ahead, negative = behind. Uses `config.now()` so `NOW` env override applies.

`GET /api/schedule/public` — renders `public_schedule.html`, a standalone page for students. Lists all `UnderEvaluationEvent` students sorted by matricola, showing their booked slot (formatted in Italian) and a pre-filled cal.com booking link (`config.CAL_URL?name=…&email=…&matricola=…`) for those without a slot. Bakes in the generation timestamp. Requires `[booking] cal_url` in config; booking links are omitted if absent.

### `views/teacher.py` — `GET /teacher`, `GET /api/teacher/file/<filename>`

Serves the exam instruction documents extracted from `PROJECTS_DIR/<exam_date>.zip`.

- `GET /teacher` — renders `teacher.html` with `files = load_project_htmls()`.
- `GET /api/teacher/file/<filename>` — returns the HTML content for the given stem (`filename` is the stem without `.html`). Content is served with `Content-Type: text/html; charset=utf-8`. Returns 404 if the stem is not in the loaded zip.

### `views/student.py` — per-student routes

- `GET /student/<email>` — renders `student.html`. Passes `email`, `name`, `matricola`, `events` (only `ExamEvent` instances — `UnderEvaluationEvent` is excluded), `current` (`UnderEvaluationEvent | None`), `slot_minutes`, `vscode_url` (`https://vscode.dev/tunnel/<tunnel><STUDENT_BASE>/<email>/source` when `[vscode] tunnel` is set and student is in current exam, else `None`), `diff_dates` (archived past-session dates with a submission from this student, most recent first, via `models.diff.past_sessions()` — empty list for non-current students, so the comparison picker only renders when relevant).
- `POST /api/<email>/note` — saves `note` (long-form, to `.md` file). Form field: `note`.
- `POST /api/<email>/mark` — saves both `mark` and `annotation` to marks.tsv via `live.mark.save()`. Form fields: `mark`, `annotation`.
- `GET /student/<email>/giustifica` — renders a standalone `giustifica.html` certificate page ready for browser print-to-PDF. Query params: `titolo` (required), `inizio` and `fine` (`HH:MM`, optional — default to slot start and slot start + `SLOT_MINUTES`). The `<email>` segment accepts a partial match: if it uniquely identifies one current-exam student the request proceeds; if ambiguous, returns `{"error": "ambiguous", "matches": [...]}` with HTTP 400.
- `GET /api/<email>/computed/files` — returns sorted JSON list of filenames in `STUDENT_BASE/<email>/computed/`; empty list if directory absent. Only available for current-exam students.
- `GET /api/<email>/computed/file?name=<filename>` — returns raw text content of one computed file; path-traversal guarded. Only available for current-exam students.
- `GET /api/<email>/diff/<old_date>/tree` — classifies the student's current source against an archived past session (`models.diff.status()`): `{added, removed, modified, raw}` (relpath lists; `raw` is true when no project template is archived for `old_date`, so the comparison fell back to unformatted source). Materializes and caches the past submission on disk on first call (see below); 404 with `{"error": ...}` if the session/student/date is invalid.
- `GET /api/<email>/diff/<old_date>/file?path=<relpath>` — returns `{"rows": [...]}` (`models.diff.file_rows()`): row-aligned, syntax-highlighted side-by-side diff data for one file — see `data.diff.align_lines()` and the `student.js` entry below. 404 if `path` isn't a real file present on both sides (also guards path traversal).
- Source/Javadoc routes delegate to `source.*` functions.

---

## Templates

Templates live at `src/examui/templates/`. Static files live at `src/examui/static/`.

**Separation of concerns**: CSS and JavaScript must live in static files (`.css` / `.js`), not embedded in templates. The only inline `<script>` block permitted in a template is a `CFG = {...}` object that bakes in server-rendered values (URLs, config) needed by the companion `.js` file. Inline `<style>` blocks are never used. Inline `style=` attributes on individual elements are acceptable for one-off layout values that don't belong in a stylesheet.

**Static file naming convention**: `base.css` and `common.js` are loaded by `base.html` and apply to every page. Page-specific overrides go in `<page>.css` / `<page>.js`. Rules that are shared across multiple pages but not universal belong in `base.css`; rules specific to a single page stay in that page's own CSS file.

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

Tree panel has a `#diff-date` select (below `#tree-filter`, only rendered when `diff_dates` is non-empty) offering "Compare to…" against each archived past session where this student has a submission. See `student.js` below for the tree-merge/diff-view behavior this drives.

Details tab: `<select id="details-select">` dropdown populated lazily on first tab open from `/api/<email>/computed/files`; selecting a filename fetches and displays its content in `<pre id="details-content">`.

Notes tab layout (top to bottom):

1. Label "Mark" + `mark-input` text field
2. Label "Note" + `annotation-input` text field
3. `note-editor` textarea (long-form notes, no label)

Status indicator is `#tab-note-status` (in the tab label itself), not a separate `#note-status` span.

---

## JavaScript

### Filter & sort persistence convention

Every list view (DataTables page) must persist its navbar filter state and sort order across navigations using `sessionStorage`. The pattern:

- A `FILTER_KEY` constant (`'<page>-filters'`).
- `saveFilters()` — serialises all filter/sort state to `sessionStorage[FILTER_KEY]`.
- `restoreFilters()` — reads `sessionStorage[FILTER_KEY]`, sets DOM controls, applies sort/search to the DataTable. Called once before the first `table.draw()`.
- An `onChange()` helper that calls `saveFilters()` then `table.draw()`, wired to each filter control's `change` event.
- `table.on('order.dt', saveFilters)` for sort persistence.
- Search input wires `saveFilters()` after `table.search().draw()`.

See `history.js` and `schedule.js` for the reference implementations. New list views must follow the same structure.

### `static/base.css`

Loaded by `base.html` on every page. Contains `.bg-orange` (Bootstrap colour extension) and the shared tab layout rules (`.tab-content`, `.tab-pane`, `.tab-pane:not(.show)`) used by any page with a tabbed view.

### `static/common.js`

Loaded by `base.html` on every page. Defines `renderMark(vm, cm)`:

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
- **Diff view**: `#diff-date` change → `onDiffDateChange()` fetches `/api/<email>/diff/<date>/tree`, stores the `{added, removed, modified}` result in `_diffStatus`, and re-renders the tree. `buildDiffTree(tree, status)` (via `mergeDiffStatus` + `insertRemovedFiles`) merges that status into the normal `_fullTree` before the existing `filterNodes`/`renderTree` pipeline runs, so diff coloring still respects the Relevant/All/Trivial filter. `insertRemovedFiles` synthesizes tree nodes for paths that only exist in the archived session (not in the current tree) and inserts them respecting the same dirs-before-files/alphabetical order as `_walk()` in `models/source.py` (`_treeSortKey`/`_insertSorted`), so they don't just get appended at the end. Rendered file nodes get a `diff-added`/`diff-modified`/`diff-removed` class and a `data-diff-status` attribute; click wiring in `applyTree()` branches on that attribute: added files load normally (`loadSourceFile`), modified files call `loadDiffFile()`, removed files call `showRemovedFile()` (a static "removed" message, no fetch — their content is never shown, per design). `loadDiffFile()` fetches `/api/<email>/diff/<date>/file?path=…` (row data, not pre-rendered HTML — deliberately not using a generic diff-library table, which looked like a different tool bolted onto the page) and `renderDiffRow()` builds each row as a real `<table>` (`.diff2-table`) row, reusing `.src`/`.src-pre`/`.src-ln`/`.src-code` inside each `<td>` so syntax highlighting (real Pygments spans, from `source.highlight_lines()`) and the `#src-fontsize` control both carry over unchanged from the normal single-file view. A real `<table>` (not flex rows) is deliberate: it gives every row's old/new columns one consistent width each and lets the whole view scroll horizontally as a single unit via `#source-code`'s own `overflow-auto`, instead of each overflowing line getting its own independent scrollbar. `skip` rows render as a `colspan="2"` "⋯ N unchanged lines ⋯" separator spanning both columns.

---

## Caching philosophy

- `@cache` used consistently throughout — never `@lru_cache` with explicit size.
- `all_students()`, `exam_date()`, `load_project_htmls()`: cached for process lifetime.
- `tree`, `all_symbols`, `file`, `deps` in `models/source.py`: cached per email (or email+relpath).
- `status`, `file_rows` in `models/diff.py`: cached per (email, old_date) / (email, old_date, relpath) — safe since archived sessions are immutable and `STUDENT_BASE` doesn't change without a process restart anyway (same caveat as `source.py`'s caches). The underlying materialized tree is additionally cached *on disk* (`WORK_DIR/diffcache/`, not just in-process) since it's the expensive part (a gradle build), and needs to survive across the several per-file requests one "Compare to…" selection triggers.
- Live I/O (`provisional`, `annotation`, `note` on `UnderEvaluationMark`) intentionally **not** cached.
- Single-worker gunicorn is a hard requirement.

---

## Data pipeline (`src/examui/pipeline/`)

Standalone Click CLI (`exam-pipeline`) that replaces the former Snakemake pipeline in the `exams/` repo. It downloads student submissions, runs automated grading (gradle test, javadoc, pygount SLOC), and assembles `marks.tsv`. Registered as a `[project.scripts]` entry point in `pyproject.toml`.

### Design decisions

- **Standalone CLI, not Flask CLI.** The pipeline imports `examui.config` for paths but does NOT create the Flask app — `create_app()` does an expensive warmup (reads all XLS, parses all source trees) that the pipeline doesn't need.
- **SQLite as ephemeral store** (`<work_dir>/pipeline.db`). Replaces the scattered JSON/TSV intermediate files from the Snakemake pipeline. Tables: `uploads`, `calendar`, `history`, `computed`. The DB can be deleted and rebuilt at any time — it is not committed to git.
- **Content hashing** (SHA-256 of each student's `consegna.zip`). Stored in the `computed` table. The `compute` command skips a student if their hash matches (unless `--force`). This replaces Snakemake's timestamp-based caching, which caused cascade reruns when files were re-downloaded with new timestamps but identical content.
- **ThreadPoolExecutor** for the `compute` step — the bottleneck is subprocess calls (gradle, pygount), not CPU-bound Python, so threads suffice. Default workers: `os.cpu_count()`.
- **Raw stdout files** stay on the filesystem at `STUDENT_BASE/<email>/computed/` so the UI's Details tab can serve them without changes. Only structured metrics go into SQLite.
- **Shared XLS parsing** via `src/examui/data/history.py`. Both `all_students()` (web app) and `collect` (pipeline) call `read_enrollments()` and `read_verbali()` — single source of truth for iscrizioni/verbali parsing.
- **Only `evals/` content is persistent.** `marks.tsv` and `notes/<email>.md` are the archival outputs (committed to git). Everything else (`work_dir/`, `pipeline.db`, `source/`, `javadoc/`, `computed/`) is ephemeral and regenerable.

### Commands

```
exam-pipeline load-history                    # populate history table from XLS files
exam-pipeline fetch-uploads                   # download + extract student submissions
exam-pipeline fetch-calendar                  # download + fuzzy-match calendar bookings
exam-pipeline compute [-s EMAIL] [-f] [-w N]  # gradle test/javadoc + pygount per student
exam-pipeline collect                         # assemble marks.tsv from DB + history
exam-pipeline run [-w N]                      # chain all five steps above
exam-pipeline status                          # show counts per table
```

All commands require `EXAMUI_CONFIG` to be set. `fetch-uploads` requires `UPLOADS_PASSWORD`, `fetch-calendar` requires `CALCOM_KEY`. `bin/pipeline` is a thin wrapper (`exec uv run exam-pipeline "$@"`); since `.envrc` does `PATH_add bin`, direnv users can run `pipeline <command>` directly instead of `uv run exam-pipeline <command>`.

The student-diff feature (comparing a current submission against an archived past session) is a Flask/web feature, not a pipeline command — see `views/student.py`, `models/diff.py`, and `data/diff.py` below.

### Data flow

```
load-history ───→ DB history table (from iscrizioni + verbali XLS)

fetch-uploads ──→ work_dir/uploaded/<email>@.../consegna.zip
                   + DB uploads table

fetch-calendar ─→ DB calendar table

compute ────────→ STUDENT_BASE/<email>/source/          (extracted project)
                   STUDENT_BASE/<email>/javadoc/          (built HTML)
                   STUDENT_BASE/<email>/computed/*.stdout  (raw output)
                   + DB computed table

collect ────────→ EVALS_DIR/<date>/marks.tsv (preserving mark/note from UI)
```

### Module structure

- `pipeline/__init__.py` — Click CLI group + all command definitions. Reads config, manages DB connection lifecycle.
- `pipeline/db.py` — SQLite schema (4 tables, all `CREATE TABLE IF NOT EXISTS`), context-managed `connect()`, typed upsert/read helpers.
- `pipeline/fetch.py` — `fetch_uploads()` (uploads API → zip → extract), `fetch_calendar()` (cal.com API → fuzzy-match → DB).
- `pipeline/compute.py` — `compute_all()` dispatches `_compute_one()` via ThreadPoolExecutor. Each student: hash check → `extract_source()` (imported from `data/extraction.py` — see below) → `gradlew test` → `gradlew javadoc` → `pygount` → upsert DB. Each student's result is committed to SQLite immediately so interrupted runs preserve finished work. Progress is shown via `rich.progress.Progress` with per-student sub-tasks showing the current step.
- `pipeline/collect.py` — `load_history()` reads XLS via shared `data.history` and populates the history table. `collect_marks()` joins all DB tables, merges with existing marks.tsv (preserving `mark`/`note` columns written by the UI), writes the result. `write_noshow()` writes `noshow.csv` (enrolled students with no submission). `noshow_emails()` returns the same list as emails.

There is no `pipeline/diff.py` — the student-diff feature is Flask-only (see below); it doesn't need a pipeline command.

### Shared data module (`src/examui/data/`)

`data/history.py` — XLS parsing extracted from `models/store.py` so both the web app and the pipeline use the same code:

- `read_enrollments(history_dir)` → `(mat2email, email2mat, names, enrollments)` from all iscrizioni XLS.
- `read_verbali(history_dir, course_name)` → list of `(matricola, date, voto, stato, name)` tuples from all verbali XLS.
- `enrolled_emails(history_dir, exam_date)` → frozenset of email usernames for one exam date.

`models/store.py`'s `all_students()` calls these shared functions and builds `Mark`/`ExamEvent`/`Student` objects. The pipeline's `collect` calls them and produces flat DB rows. Same parsing logic, no duplication.

`data/extraction.py` — `extract_source(email, consegna, template_zip, source_dir)`: overlays a student's `consegna.zip` onto a project template and runs `spotlessApply`, writing into an explicitly-passed `source_dir` (not hardwired to `STUDENT_BASE`). Used by `pipeline/compute.py` for the current exam and `data/diff.py` for archived past sessions.

`extract_source()` runs `_strip_leading_comment()` on every extracted `.java` file before `spotlessApply`: spotless's `licenseHeaderFile` step locates the old header by cutting the file, as text, at the first line starting with `package`/`import` — it has no notion of comment structure. If a student's leading block comment doesn't close before that line (glued straight into `package`/`import` with no newline, e.g. `*/package foo;`; or spanning past it entirely, even wrapping the whole file), the cut still lands past the comment's true close, so the kept tail retains a `*/` with no matching opener and the reformatted file no longer compiles. This is a real, pre-existing bug in the extraction path (affects `compute`'s normal per-exam processing too, whenever a student's header happens to be malformed like this) — first noticed while building the student-diff feature, because that re-exposed a never-before-formatted archived submission to it; a second, more severe variant (a whole-file leading comment) surfaced later via davide.ciaramidaro's 2026-09-11 submission, whose `Main.java` was entirely wrapped in one unclosed comment. `_strip_leading_comment()` removes the whole leading comment (correct without tracking nesting, since Java's `/* */` doesn't nest) before spotless ever sees the file, so its cut always lands on real code. In the degenerate case where a student's "code" is entirely commented out, the file is left empty (still valid Java) rather than broken — `licenseHeaderFile` then lint-fails on that one file (no `package`/`import`/`class` left to anchor on), which `extract_source` doesn't check the exit code for, so that file alone is left without a license header while the rest of the module's files still get formatted normally.

`_strip_leading_comment()` skips `package-info.java`/`module-info.java`. Their leading comment is the package/module's own required Javadoc, not a license-header slot — spotless's `licenseHeaderFile` step never touches headers on these two filenames (confirmed empirically: it leaves them alone even when no header is present at all to replace). Stripping it there deleted required Javadoc that nothing put back, so every affected package failed `javadoc -Werror` with "no comment" — caught immediately after the `_unglue_headers` → `_strip_leading_comment` rewrite via a `pipeline compute -f` rerun, which re-exposed it across most of the 2026-09-11 cohort (see tommaso.bromuri, 41286A).

`data/diff.py` — no gradle/Flask coupling, just plain functions operating on `Path`s passed in explicitly, used by `models/diff.py` (below) to back the Flask app's student-diff feature:

- `extract_backup_consegna()` / `list_sessions_with_submission()` — parse `backup_dir/<date>.zip` (pure zip I/O).
- `materialize_consegna()` / `source_root()` — extract-and-format (or raw-extract) a consegna into a plain java tree, via `extraction.extract_source()`.
- `classify_files(old_root, new_root)` — compares two source trees ignoring blank-line-only differences; returns relpath lists for added/removed/modified.
- `align_lines(old_lines, new_lines, context)` — pure `difflib.SequenceMatcher`-based line alignment with unchanged runs collapsed to `context` lines; used by `models/diff.py` to build the web UI's syntax-highlighted row data (below). Doesn't know about blank-line filtering, Pygments, or HTML — just aligns whatever line sequences it's given.

### Web-side diff model (`src/examui/models/diff.py`)

Where the Flask app's `/api/<email>/diff/*` routes (see `views/student.py` above) get their data. The web UI caches each archived session's materialized tree on disk at `WORK_DIR/diffcache/<email>/<old_date>/source/` (`_ensure_old_root()`) — extraction only happens (and only pays the `spotlessApply`/gradle cost) once per (student, past session) the first time it's requested; the browser then makes several follow-up per-file requests while the examiner clicks around the tree, which must stay fast. A `.raw` marker file records whether that session had to fall back to unformatted extraction (no archived template). Nothing here mutates `STUDENT_BASE` — only the new `diffcache/` subtree.

- `past_sessions(email)` — used by `views/student.py`'s `student()` to populate `diff_dates` (empty list skips rendering the picker entirely).
- `status(email, old_date)` — `@cache`; wraps `data.diff.classify_files()` against `STUDENT_BASE/<email>/source`.
- `file_rows(email, old_date, relpath)` — `@cache`; wraps `data.diff.align_lines()`, then swaps its raw line-number output for `source.highlight_lines()`-rendered HTML — see the `student.js` entry above for how those rows get rendered as a native-looking two-column view instead of a bolted-on diff-library table.

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
