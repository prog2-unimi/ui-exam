# ui-exam — developer notes

The Python package, imported and run as `uiexam`, is the app; `ui-exam` is its
name everywhere a person sees one. `README.md` is the user-facing map (what it
offers, the configuration file, how to run it); these notes hold what the code
cannot show. Per-function behaviour is in the docstrings and comments beside the
code, not here.

## Purpose

Flask web application used during oral exams for PROGRAMMAZIONE II. It shows
each student's exam history, lets the examiner take notes and record a
provisional mark, and displays the student's submitted Java source code (syntax
highlighting, symbol navigation, dependency graph, Javadoc).

Runs as a dhevmera host app: @~/.claude/apps.md

## Layout

- `models/` — `events.py` pure frozen data classes, `store.py` all I/O of
  history and live marks, `source.py` student source and Javadoc, `diff.py` the
  comparison with archived sessions.
- `lang/` — Java analysis with tree-sitter, no I/O, no Flask, no config: unit
  testable standalone.
- `data/` — XLS parsing, source extraction and diff helpers shared by the web
  app and the pipeline; plain functions on explicit `Path`s.
- `pipeline/` — the `exam-pipeline` CLI; `views/`, `templates/`, `static/` — the
  web side.

## Configuration

`config.py` reads `config.toml` in the checkout, or the file `UIEXAM_CONFIG`
names (the unit sets neither `.env` nor that variable). The keys are in
`config.toml.example` and `README.md`. Values under `[paths]` may name
environment variables (`${APP_HOME}`), which must be set (`ConfigError`
otherwise): `APP_HOME` is the app's home, given by the unit and exported by
`.env` for hand-run tools.

Every key is mandatory except `trivial_packages` and `titoli`, which fall back
to defaults. `_get(section, key, default_value)` raises `ConfigError` naming the
section, key and file, so a misconfiguration fails at import time rather than as
an `AttributeError` deep in a view. This holds even for keys of optional UI
features (`vscode.tunnel`, `booking.cal_url`) and of pipeline-only sections
(`uploads`, the pipeline `booking` keys): every deployment fills the whole file.

Two paths are derived, with no TOML key: `STUDENT_BASE` is `work_dir/student`,
`PROJECTS_DIR` is `history_dir/projects`.

`backup_dir` is unrelated to the others: manually maintained archives of _raw_
past-session uploads, one `<YYMMDD>.zip` per exam date holding every student's
numbered `<email>@domain/NNN-consegna.zip` resubmissions as received (not the
single latest copy the pipeline keeps in `work_dir/uploaded`). Only the web
app's diff feature reads it.

`TODAY` (`YYMMDD`) and `NOW` (`HHMM`) are environment variables outside the
TOML, simulation overrides: `TODAY` selects the day whose slots are shown, `NOW`
the time `/api/pace` uses (`config.now()`), e.g.
`TODAY=260615 NOW=1145 ./bin/debug`.

Secrets are `KEY=value` lines of `~/.config/ui-exam/ui-exam.env`, loaded by
`.envrc` (`dotenv`) for the hand-run tools; the Flask app uses none:

- `UPLOADS_PASSWORD` — `fetch-uploads`, the uploads API password.
- `CALCOM_KEY` — `fetch-calendar`, the cal.com API bearer token.
- `MOSS_USERID` — `bin/moss`, a MOSS account id.

## Running

### Local development

`source .env` (or `direnv allow`), then `./bin/debug`: gunicorn with
`--workers=1 --reload` on `127.0.0.1:8765`. `.env` must export `APP_HOME` and
`config.toml` be populated.

### Remote access from the tablet or phone

svm runs the app as a dhevmera host app, `ui-exam.service`, started by hand
(`dhapp start ui-exam` before an exam, `dhapp stop ui-exam` after) and reached
on the tailnet at `https://ui-exam.robin-diatonic.ts.net`, a home-screen icon in
Chrome on the tablet, opened by a session with `dhremote url <address>`. The
unit runs
`.venv/bin/gunicorn -c gunicorn.conf.py --bind 127.0.0.1:8765 uiexam:create_app()`
(the command line overrides `gunicorn.conf.py`'s `bind`); it runs until stopped.
`dhapp show ui-exam` gives the entry and `~/.claude/apps.md` the contract; code
changes go live with `dhapp deploy ui-exam`. Logs are `dhapp logs ui-exam` (the
journal).

The app's home, `APP_HOME` (`/chome/santini/AppsData/ui-exam`, backed up
nightly), holds `po/` (the work directory) and links `history`, `evals` and
`backup` to the course's directories; `config.toml` names them through
`${APP_HOME}`. `bin/giustifica` still reads `UIEXAM_PORT`.

**Single-worker gunicorn is a hard requirement**: `@cache` holds process-local
state, and the live marks are written by the same process that reads them. The
unit takes `workers` from `gunicorn.conf.py`, which says `workers = 1`.

### `bin/` scripts

- `bin/publish` — deploys the public schedule page. It starts a throwaway
  gunicorn on port 8766 (the app on 8765 may be stale or stopped), polls
  `/api/schedule/public` until the warmed-up app answers (`create_app()` warms
  up synchronously before gunicorn binds, so an answer means ready), fetches the
  page (`--tba` for the placeholder version), kills the server, writes a
  `netlify.toml` that suppresses any build command, and runs
  `netlify deploy --prod` to `prog2unimi-esame.netlify.app`. `NETLIFY_SITE_ID`
  comes from `.env`; `NETLIFY_AUTH_TOKEN` from the environment
  (`~/.bash_secrets` is sourced when present).
- `bin/giustifica <email-fragment> <titolo> [inizio] [fine]` — fetches a
  giustifica from the running app with `curl` and saves
  `giustifica-<fragment>.html`; the server resolves a partial address and lists
  the candidates when it is ambiguous.
- `bin/moss <students_dir> [--exclude DIR ...] [--filter REGEX] [--dry-run]` —
  submits sources to MOSS. A standalone script (not part of the package) with an
  `env -S uv run` shebang; unlike the other `bin/` scripts it does not source
  `.env`, so `MOSS_USERID` must already be in the environment (`direnv allow`).
- `bin/pipeline` — wrapper for `uv run exam-pipeline`; `bin/clean` removes
  `__pycache__` and tool caches (`PYTHONDONTWRITEBYTECODE=1` in `.env` prevents
  most).

### Tests and formatting

`uv run pytest tests/` (pure Python: no gradle, graphviz or JDK). Only `lang/`
and `data/` have tests; `views/`, `models/store.py`, `source.py` and `pipeline/`
have none. CI (`.github/workflows/tests.yml`) runs the same plus coverage,
reported for reference only (no threshold).

Formatters are pinned in the `dev` group and run by pre-commit; after cloning,
`uv sync` then `uv run pre-commit install`; format everything with
`uv run pre-commit run --all-files`. Not formatted: the Jinja templates
(Prettier does not understand `{% %}`) and `static/pygments.css`, which
`create_app()` rewrites at every startup. TOML goes through taplo (never
`uv.lock`).

______________________________________________________________________

## Data sources and what they mean

### `history_dir/iscrizioni/*.xls`

One XLS per exam session, named `YYMMDD.xls`; the stem is the exam date used as
a key everywhere. Each row is an enrolled student (`Matricola`, `Email` as
username only, `Cognome`, `Nome`). The **most recent** stem is `exam_date()`,
the current exam. A student enrolled but absent from the verbali for a date gets
`ExamEvent(date, mark=None)`.

### `history_dir/verbali/*.xls`

Registrar verbali: one row per student who sat an exam and got a result. Only
rows whose `Descrizione insegnamento` matches `config.COURSE_NAME`
(case-insensitive) count. Marks are decoded by `Mark.from_verbale`.

### `evals_dir/<date>/marks.tsv`

One row per student who turned in source for the exam, pre-populated by the
pipeline's `collect` at exam start. Only `mark` (provisional vote: `AS`, `RE`,
numeric) and `note` (short pre-exam comment) are ever written by the UI; every
other column (`email`, `regnum`, metrics, `date` slot and `upload`
`YYMMDD-HHMM`) is read-only, and `rej`/`acc`/`other` are ignored by the UI. The
columns are `_MARKS_COLUMNS` in `pipeline/collect.py`.

**Source presence is decided by marks.tsv, not the filesystem**: an email in it
yields an `UnderEvaluationEvent` as the student's first event; enrolled but
absent gives `ExamEvent(date, mark=None)` for the current date. A missing file
means every enrolled student is absent (exam not yet prepared).

**Operational constraint:** `marks.tsv` is read only for `exam_date()`. Once a
newer iscrizioni XLS is added, past `evals/<date>/marks.tsv` data (provisional
marks, metrics) disappears from the UI, and a past notes file still adds its
date to the history but, with no verbale entry, renders as absent and its note
is not attached. Download the verbali for a past exam **before** creating the
next exam's iscrizioni; once the verbale is in place, notes reattach.

### `evals_dir/<date>/notes/<email>.md`

Long-form examiner notes, written live by the UI; lines starting with `#` are
stripped on save, and the file is created or deleted as needed. Past dates'
notes are read once at startup and baked into `Mark.note`; the current exam's
are read and written live through `UnderEvaluationMark.note`.

### `STUDENT_BASE/<email>/`

`source/` is the submitted Java project (Maven layout: the source root is
`src/main/java` under it when that exists, else `source/` itself); `javadoc/`
the pre-built HTML tree, served statically; `computed/` optional plain-text
outputs of the automated grading, listed and served read-only by the Details
tab, uncached.

______________________________________________________________________

## Data model

`models/events.py` holds the pure frozen dataclasses, `models/store.py` all the
I/O. Things the signatures do not say:

- `events` of a `Student` is **most-recent-first**; do not `reversed()` it for
  the latest. A student is in the current exam when `events[0]` is an
  `UnderEvaluationEvent`; there is no separate `current` field.
- `Student.summary_mark` is the most notable past verbale mark: first `passato`,
  else first `rifiutato`, else first `respinto`/`ritirato`, else `None`.
- `UnderEvaluationEvent.metrics` is a frozen snapshot of the marks.tsv row at
  `all_students()` time; `.mark` is a live read/write proxy (`provisional`,
  `annotation` on the TSV, `note` on the `.md`) and is deliberately uncached.
  `_write_tsv` rewrites the whole file.
- Provisional marks are free-form strings typed by the examiner (`18`, `RE`,
  `RI`), not `Mark` objects.

Mark kinds from a verbale (`Mark.from_verbale`):

- `passato` — numeric voto, stato `V`.
- `rifiutato` — numeric voto, any other stato (refused by the student).
- `respinto` — voto `RE*`, no value.
- `ritirato` — voto `RI*`, no value.

`ExamEvent.mark is None` means the student was absent.

## Caching

- `@cache` throughout, never `@lru_cache` with a size. `all_students()`,
  `exam_date()` and `load_project_htmls()` live for the process;
  `models/source.py` caches per email (or email and relpath), all warmed up at
  startup for the students under evaluation (`file` excepted).
- `models/diff.py` caches `status` and `file_rows` per (email, old date\[,
  relpath\]), safe because archived sessions are immutable. The expensive part,
  the materialized past tree (a gradle build), is also cached on disk under
  `work_dir/diffcache/`, so it survives the several per-file requests one
  "Compare to..." triggers.
- Live marks and notes are never cached. Single worker: see Running.

______________________________________________________________________

## Java analysis (`src/uiexam/lang/`)

`parsing.py` (tree-sitter) and `graph.py` (Tarjan SCCs, transitive reduction,
triviality) are heuristic, not a Java scope resolver. Triviality: a name ending
`Exception`/`Error`/`Client`, a package in `trivial_packages`, or inheriting
transitively from a trivial type. It is judged per declared type (nested ones
too), keyed by `fqn`, never inherited from a container. A **file** is trivial
only if every type it declares is; `deps()` filters per type instead.

Known quirks (tests document them):

- **Primitive types are not in `uses`**: `_collect_type_refs` visits only
  `type_identifier`; `int`, `double` are `integral_type`/`floating_point_type`
  nodes, so they never appear in any `uses` set. Tests asserting on parameter,
  return or local uses need reference types.
- **Abstract class detection is broken**: `child_by_field_name('modifiers')` is
  `None` for `class_declaration` in the installed tree-sitter-java, so
  `class_uses` returns `kind='class'` even for `abstract class`; the
  `'abstract'` kind is dead until upstream or the parsing changes.
- **Static access by uppercase heuristic**: `_walk_uses` takes a
  `method_invocation`/`field_access` whose object is a plain identifier starting
  uppercase for a static use of a class (added to `local`). It relies on
  PascalCase/camelCase naming; without it utility classes with only static
  methods would vanish from the dependency graph. Dotted type references
  (`Outer.Inner`) use the same convention to decide whether the first segment is
  a local type or an already fully qualified path.
- Local and anonymous classes are not reported by `class_uses` (no stable name).

## Source analysis (`models/source.py`)

Orchestrates `lang`, Pygments and Graphviz. `deps()` has one node per declared
type, so a file with nested types has several nodes mapped to the same relpath
(many-to-one: the JS handles it), each with its own declaration line, so a click
scrolls to that type. A nested type is labeled `Container.Name` and linked to
its container by a dotted, undirected `constraint=false` edge, deliberately not
a nested Graphviz cluster: a nested type's dependency cycle can span outside its
container, clusters must nest hierarchically or the layout breaks, and the
dotted edge composes with SCC clustering and does not disturb the dependency
rank. SCCs and transitive reduction run over the full node set and ignore the
containment edges.

`models/diff.py` never mutates `STUDENT_BASE`; it writes only `diffcache/`. A
`.raw` marker records that a session had no archived project template and fell
back to unformatted source.

______________________________________________________________________

## Views and templates

Routes are in `views/*.py`; their handlers and docstrings are the reference.
Behaviour worth knowing:

- `/api/pace` reads `provisional` live; `visible` is false with no slots today,
  more than 60 minutes before the first slot, or when everyone has a mark.
  `delta` is minutes from now to the first unmarked slot (positive = ahead).
- `/student/<email>/giustifica` accepts a partial email, answering HTTP 400 with
  the matches when it is ambiguous.
- `/api/schedule/public` is the standalone student-facing page (matricola and
  slot only, no names or marks) baked at generation time; `bin/publish` deploys
  it.
- `/manifest.webmanifest` is a route, not a static file, so its scope is `/`.
  The standalone pages (`giustifica.html`, `public_schedule.html`) do not extend
  `base.html` and link neither the manifest nor the icon.
- The Jinja `student.html` reads the provisional mark once
  (`current.mark.provisional`) and reuses it.

**Separation of concerns**: CSS and JavaScript live in static files, never in
templates. The only inline `<script>` allowed is a `CFG = {...}` object baking
in server-rendered values for the page's `.js`; no inline `<style>`; inline
`style=` on single elements is fine for one-off layout. `base.css` and
`common.js` load on every page and hold what is shared by several pages;
page-specific rules go in `<page>.css`/`<page>.js`.

**Filter and sort persistence**: every DataTables list view persists its filter
state and sort order across navigations in `sessionStorage['<page>-filters']`:
`saveFilters()` serialises, `restoreFilters()` runs once before the first
`table.draw()`, an `onChange()` helper calls `saveFilters()` then `draw()` on
each filter's `change`, `table.on('order.dt', saveFilters)` covers sorting, and
the search input saves after `search().draw()`. `history.js` and `schedule.js`
are the reference; new list views follow them.

**Diff view** (`student.js`): `#diff-date` merges the added/removed/modified
status into the normal tree before the usual filtering, so colouring respects
the Relevant/All/Trivial filter. Removed files show only a static message, their
content is never shown by design. The side-by-side view is a real `<table>`
reusing `.src` markup, not flex rows and not a diff library's table: every row's
old/new columns share one width, the whole view scrolls horizontally as one
unit, and highlighting and the `#src-fontsize` control carry over from the
single-file view.

______________________________________________________________________

## Data pipeline (`src/uiexam/pipeline/`)

`exam-pipeline` (Click; `bin/pipeline`) downloads submissions, grades them
(gradle test and javadoc, pygount SLOC) and assembles `marks.tsv`. `--help`
lists the commands; `run` chains them in order: `load-history`, `fetch-uploads`,
`fetch-calendar`, `compute`, `collect`. All need `APP_HOME`; `fetch-uploads`
needs `UPLOADS_PASSWORD`, `fetch-calendar` `CALCOM_KEY`.

Why it is built this way:

- **A standalone CLI, not a Flask command**: it imports `uiexam.config` for
  paths but never `create_app()`, whose warmup parses every XLS and source tree.
- **SQLite as an ephemeral store** (`work_dir/pipeline.db`): one place instead
  of the scattered JSON/TSV intermediates of the former Snakemake pipeline. It
  can be deleted and rebuilt at any time and is not committed.
- **Content hashing** (SHA-256 of each `consegna.zip`, in the `computed` table):
  `compute` skips a student whose hash is unchanged unless `--force`. Timestamps
  caused cascade reruns when identical files were downloaded again.
- **ThreadPoolExecutor** in `compute`: the cost is subprocesses (gradle,
  pygount), not Python CPU. Each student's result is committed at once, so an
  interrupted run keeps finished work.
- **Raw stdout stays on the filesystem** at `STUDENT_BASE/<email>/computed/` for
  the Details tab; only structured metrics go into SQLite.
- **Only `evals/` is persistent** (`marks.tsv`, `notes/<email>.md`, committed to
  git). `work_dir/`, `pipeline.db`, `source/`, `javadoc/` and `computed/` are
  regenerable. `collect` merges into an existing `marks.tsv` preserving the
  `mark` and `note` columns the UI wrote.
- **One XLS parser**: `data/history.py` serves both `all_students()` and
  `collect`.

`data/extraction.py` overlays a student's `consegna.zip` onto a project template
and runs `spotlessApply`, into a destination passed explicitly; the pipeline's
`compute` and the web diff both use it.

`_strip_leading_comment()` runs on every extracted `.java` file first because
spotless's `licenseHeaderFile` cuts the old header at the first line starting
`package`/`import`, with no notion of comment structure: a student's leading
block comment that does not close before that line (glued into `package`, or
wrapping the whole file) leaves a stray `*/` and a file that no longer compiles.
It skips `package-info.java` and `module-info.java`, whose leading comment is
the required Javadoc and which spotless never touches, so stripping it would
break `javadoc -Werror`. A file that is entirely commented out is left empty,
which `licenseHeaderFile` then lint-fails alone.

## Configured with dhevmera

This repository's Claude Code configuration — this file, `.claude/memory/`,
`.claude/settings*.json` — is managed with dhevmera. Read `~/.claude/CLAUDE.md`,
the global instructions, first; nothing here repeats it.

The lines below import the aims this repository's work belongs to, from
dhevmera's `files/claude/dirs/aims/`:

@~/.claude/aims/teaching.md

Last reviewed on 2026-11-07 against dhevmera 54ca10caefd4.
