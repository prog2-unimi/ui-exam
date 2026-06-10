# examui — developer notes

## Purpose

Flask web application used during oral exams for PROGRAMMAZIONE II. It shows each student's exam history, lets the examiner take notes and record a provisional mark, and displays the student's submitted Java source code (with syntax highlighting, symbol navigation, dependency graph, and Javadoc).

## Running

```bash
HISTORY_DIR=... EVALS_DIR=... STUDENT_BASE=... ./run.sh
```

Runs gunicorn with `--workers=1` (single process — required because in-process `@cache` is the caching layer). `SLOT_MINUTES` defaults to 30.

---

## Data sources and what they mean

### `HISTORY_DIR/iscrizioni/*.xls`

One XLS per exam session, named `YYMMDD.xls` (the stem is the exam date used everywhere as a key). Each row is a student enrolled for that session. Columns: `Matricola`, `Email` (username only, no domain), `Cognome`, `Nome`.

- A student present here but absent from verbali for that date → mark `AS` (assente).
- The **most recent** XLS stem is `exam_date()` — the current/live exam.

### `HISTORY_DIR/verbali/*.xls`

Registrar verbali. Each row is a student who sat an exam and got a result. Columns include `Matricola`, `Voto` (grade), `Stato Esito` (outcome state), `Data appello` (date), `Descrizione insegnamento`. Only rows where `Descrizione insegnamento == 'PROGRAMMAZIONE II'` are used.

Mark encoding from verbali: first two chars of `Voto` uppercased + first char of `Stato Esito`. Examples:
- `19V` = 19 passed (verbale)
- `19R` = 19 refused by student (tilde ~)
- `REV` / `RIV` etc. = rejected/withdrawn

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
| `code` | R/O | Lines of code |
| `docs` | R/O | Lines of Javadoc |
| `file` | R/O | Number of files |
| `ccode` | R/O | Lines per class |
| `cfile` | R/O | Files per class |
| `date` | R/O | Booked oral slot (`YYMMDD-HHMM`) |
| `upload` | R/O | Submission timestamp (`YYMMDD-HHMM`) |
| `num` | R/O | Count of past non-AS results |
| `rej`/`acc`/`other` | R/O | Ignored by the UI |

**Source presence is determined by marks.tsv, not the filesystem.** If a student's email appears in marks.tsv, they are `LiveCurrentExamEvent`. If enrolled (in iscrizioni) but absent from marks.tsv, they are `AbsentCurrentExamEvent`. No filesystem check is needed.

- Missing file → all enrolled students are `Absent` (exam not yet prepared).
- File exists but student row is missing → `RuntimeError` (invariant violation).
- Only `mark` and `note` columns are ever modified by the UI; all other columns are read-only.

### `EVALS_DIR/<date>/notes/<email>.md`

Long-form examiner notes for a student at a given exam date. Written live by the UI. Lines starting with `#` are stripped on save. Created/deleted as needed.

Past exam notes are read once at startup (baked into `Student.events`). Current exam long notes are read/written live via `LiveCurrentExamEvent.long_note`.

### `STUDENT_BASE/<email>/source/`

Student's submitted Java project. Layout:
- If `source/src/main/java/` exists → that is the source root (Maven layout).
- Otherwise `source/` itself is the source root.

### `STUDENT_BASE/<email>/javadoc/`

Pre-built Javadoc HTML tree, served as static files by the `/api/<email>/javadoc/` route.

---

## Data model (`src/examui/models/history.py`)

### `ExamEvent` — a past exam event (frozen dataclass)

```python
@dataclass(frozen=True)
class ExamEvent:
    date: str        # 'YYMMDD'
    mark: str        # 'AS' | '19V' | '19R' | 'REV' | 'RIV' | ...
    note: str | None # long-form oral note from that session
```

### `Metrics` — read-only snapshot of marks.tsv static fields (frozen dataclass)

```python
@dataclass(frozen=True)
class Metrics:
    tests: str; javadoc: str; cyclic: str
    code: int; docs: int; file: int; ccode: int; cfile: int
    slot: str    # booked oral time ('YYMMDD-HHMM' or '')
    upload: str  # submission time ('YYMMDD-HHMM' or '')
    num: int     # count of past non-AS results
```

Built once at `all_students()` time from the marks.tsv row. Immutable for the process lifetime.

### `AbsentCurrentExamEvent` — enrolled this exam, not in marks.tsv

`mark` always `'AS'`. `short_note` and `long_note` return `''`. All setters raise `AttributeError`.

### `LiveCurrentExamEvent` — enrolled this exam, present in marks.tsv

Has a `metrics: Metrics` attribute (frozen, from marks.tsv row at build time).

R/W live properties:
- `mark` — reads/writes marks.tsv `mark` column.
- `short_note` — reads/writes marks.tsv `note` column.
- `long_note` — reads/writes the `.md` file in the notes directory.

Both marks.tsv updates go through `_update_marks_tsv()` which reads and rewrites the whole file in one operation, accepting keyword-only `mark` and/or `short_note` arguments.

### `Student` — frozen dataclass

```python
@dataclass(frozen=True)
class Student:
    email: str; matricola: str; name: str
    events: list[ExamEvent]   # past events, most-recent-first
    current: AbsentCurrentExamEvent | LiveCurrentExamEvent | None
```

`current is None` → student not enrolled in the current exam.

`Student.verbali_mark` property — summary dict for the mark badge:
- `{'value': '19', 'kind': 'pass'}` — first passing grade
- `{'value': '19~', 'kind': 'tilde'}` — most recent refused (tilde)
- `{'value': 'RE'/'RI', 'kind': 'RE'/'RI'}` — most recent rejected/withdrawn
- `None` — no notable history

`events` is most-recent-first. Do not use `reversed()` when you want the most recent entry.

### `all_students()` — `@cache`

Reads all iscrizioni XLS, all verbali XLS, past notes, and current marks.tsv once at startup. Builds the full `dict[email, Student]`. Determines `Live` vs `Absent` from marks.tsv presence (no filesystem check).

### `exam_date()` — `@cache`

Returns the stem of the most recent iscrizioni XLS (`YYMMDD`).

---

## Source analysis model (`src/examui/models/oral.py`)

All functions are `@cache`-decorated — computed once per process, warmed up at startup for all `LiveCurrentExamEvent` students.

- `source_tree(email)` — directory tree as JSON-serialisable list.
- `source_all_symbols(email)` — flat list of all symbol dicts across non-trivial files.
- `source_file(email, relpath)` — Pygments-highlighted lines + symbols for one file.
- `source_deps(email)` — dependency graph `{'svg': ..., 'paths': {node_id: relpath}}`. Uses Tarjan SCC + transitive reduction + Graphviz.
- `warmup(email)` — eagerly populates all four caches. Called at startup.

"Trivial" files/dirs (Exceptions, Error subclasses, `clients/`) are excluded from the symbol index and dependency graph.

---

## Views

### `views/history.py` — `GET /history`

All students enrolled at least once (past or current exam). Only `verbali_mark` in the mark column — no provisional marks, no current-exam data. Passes `students_json`, `exam_dates` (past dates only) to `history.html`.

### `views/schedule.py` — `GET /schedule`

All `LiveCurrentExamEvent` students for the current exam. Includes full `Metrics` fields plus `verbali_mark` and `current_mark`. Sorted by `slot`. Passes `rows_json`, `exam_date`, `today` (`YYMMDD`) to `schedule.html`.

### `views/student.py` — per-student routes

- `GET /student/<email>` — renders `student.html`.
- `POST /api/<email>/note` — saves both `short_note` (to marks.tsv) and `long_note` (to `.md` file) from a single form POST.
- `POST /api/<email>/mark` — saves `mark` to marks.tsv.
- Source/Javadoc routes delegate to `oral.*` functions.

---

## Templates

### `base.html`
Bootstrap 5 + Bootstrap Icons CDN.

### `history.html`
DataTables. `CFG = {students: [...]}`. Filters: date, has-~ checkbox. Links to `/schedule` and to `/student/<email>`. Filter state in `sessionStorage['history-filters']`.

### `schedule.html`
DataTables. `CFG = {rows: [...], today: 'YYMMDD'}`. Columns: slot, name, mark, tests, javadoc, cyclic, code, docs, files, past attempts. "Today only" checkbox filter. Links to `/history` and to `/student/<email>`.

### `student.html`

Key pattern at top:
```jinja
{% set cm = current.mark if current else none %}
```
Single read of marks.tsv, reused for all conditional logic.

Tab visibility: History always visible. Note/Source/Deps/Javadoc enabled only when `cm != none and cm != 'AS'` (i.e. student is `LiveCurrentExamEvent` with a non-AS mark).

Notes tab layout (top to bottom):
1. `mark` input + status span
2. Label "Note" + `short_note` input + status span (same `note-status` as above)
3. `long_note` textarea (no label)

---

## JavaScript

### `static/history.js`
DataTables for history list. `renderMark(vm)` — verbali_mark badge only. Filter state in `sessionStorage['history-filters']`.

### `static/schedule.js`
DataTables for schedule. `renderMark(vm, cm)` — verbali_mark badge + provisional yellow badge + `??`. `mkBadge(val, okVal)` — green/red badge for tests/javadoc/cyclic. "Today only" filter checks `row.slot.startsWith(CFG.today)`.

### `static/student.js`
- **Timer**: `sessionStorage['examTimer'] = {email, startMs, slotMs}`. Progress bar at 80/90/95%.
- **Note save**: single `POST /api/<email>/note` with both `short_note` and `long_note`. Debounced 2 s + blur for both inputs. Status shown in `#note-status`.
- **Mark save**: `POST /api/<email>/mark` on blur/Enter.
- **Source tree, symbol search, file viewer, deps graph, Javadoc**: unchanged from original.
- **Font size**: `localStorage['oral-src-font-size']`.

---

## Caching philosophy

- `@cache` used consistently throughout — never `@lru_cache` with explicit size.
- `all_students()`, `exam_date()`: cached for process lifetime.
- `source_tree`, `source_all_symbols`, `source_file`, `source_deps`: cached per email.
- Live I/O (`mark`, `short_note`, `long_note`) intentionally **not** cached.
- Single-worker gunicorn is a hard requirement.

---

## Mark string conventions

| Mark   | Meaning                          |
|--------|----------------------------------|
| `AS`   | Assente (absent / not in marks.tsv) |
| `??`   | marks.tsv not yet prepared       |
| `19V`  | 19 passed (verbale V)            |
| `19R`  | 19 refused by student (~ tilde)  |
| `REV`  | Rejected (respinto)              |
| `RIV`  | Withdrawn (ritirato)             |
| `RI?`  | Withdrawn provisional            |
| `RE?`  | Rejected provisional             |

`verbali_mark` uses `mark[-1:] == 'V'` for pass, `mark[-1:] == 'R' and mark[:2] not in ('RI','RE')` for tilde, `mark[:2] in ('RE','RI')` for rejected/withdrawn. Events are most-recent-first so `next()` finds the most recent match.
