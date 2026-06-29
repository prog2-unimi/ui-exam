# examui

A Flask web application for assisting oral exam sessions in the
[Programmazione II](https://prog2.di.unimi.it) course at Università degli Studi di Milano.

Given a student's submitted source code and generated Javadoc, it provides:

- a searchable history of all past exam events per student;
- a per-session oral page with a note editor, syntax-highlighted source navigator
  (with symbol search and Javadoc deep-links), dependency graph, Javadoc viewer,
  and a Details tab for computed auxiliary files;
- a schedule view with slot assignments, pace tracking, and actions (BCC email, giustifica, SIFA CSV export);
- a teacher view displaying exam instruction documents (HTML files from a per-session zip archive) in a tabbed iframe layout;
- a public-facing booking page (deployed to Netlify) listing admitted students with
  pre-filled cal.com booking links.

> **Note:** This is preliminary software, developed for personal use during exam
> sessions. Interfaces and data formats may change without notice.

## Configuration

Copy `config.toml.example` to `config.toml` and fill in your values:

```toml
[paths]
history_dir  = "/path/to/exams/history"
evals_dir    = "/path/to/exams/evals"
projects_dir = "/path/to/projects"        # enables the Teacher view
work_dir     = "/path/to/work/dir"        # ephemeral directory for pipeline artifacts

[exam]
slot_minutes     = 30
trivial_packages = ["client", "clients", "util", "utils"]
course_name      = "Programmazione II"
course_degree    = "Informatica"       # optional, for giustifica

[vscode]
tunnel = "santinivm"                   # optional; enables "Open in VSCode" button

[booking]
cal_url  = "https://cal.com/user/event" # optional; enables public schedule page
endpoint = "https://api.cal.com/v2/bookings"  # for pipeline
version  = "2024-08-13"                       # for pipeline
event    = 1234567                            # for pipeline

[actions]
teacher_email  = "teacher@example.com"
teacher_name   = "Name Surname"
subject_prefix = "[CourseCode] "
email_domain   = "students.university.edu"
titoli         = ["lo studente", "la studentessa", "il dottore", "la dottoressa"]

[uploads]                              # for pipeline
url      = "https://api.upload.di.unimi.it/admin"
username = "teacher@university.edu"
session  = 1234
```

Then copy `.envrc.example` to `.envrc` and set at minimum:

```shell
export EXAMUI_CONFIG="$(pwd)/config.toml"
# Required for bin/publish (Netlify deployment):
export NETLIFY_AUTH_TOKEN=<personal-access-token>
export NETLIFY_SITE_ID=<site-id>
```

Two additional env vars are available for development time simulation (not in the TOML):

| Variable | Format | Effect |
|----------|--------|--------|
| `TODAY`  | `YYMMDD` | Overrides the date used to select the active exam session |
| `NOW`    | `HHMM`   | Overrides the current time used by `/api/pace` |

## Usage

```shell
direnv allow   # or: source .envrc
./bin/debug
```

The app listens on `127.0.0.1:8765`.

### Remote access from a tablet (Termux)

Add the following to `~/.ssh/authorized_keys` on the exam host, pointing at the
absolute path of `bin/server`:

```
command="/path/to/bin/server",no-pty,no-agent-forwarding,no-X11-forwarding,permitopen="localhost:8765" ssh-ed25519 AAAA...
```

Add the client-side variables to `.envrc` (or a separate `.envrc` on the tablet):

```shell
EXAMUI_HOST=svm        # SSH host alias from ~/.ssh/config
EXAMUI_KEY=~/.ssh/id_examui
EXAMUI_PORT=8765
```

Then on the tablet:

```shell
./bin/client
```

This opens the SSH tunnel, waits for gunicorn to be reachable, launches the
browser, and tears everything down on Ctrl-C.

### `bin/publish` — deploy the public schedule page

Fetches the generated public schedule page from the running app and deploys it
to the Netlify site configured via `NETLIFY_SITE_ID` and `NETLIFY_AUTH_TOKEN`
in `.envrc`. Requires the Netlify CLI (`npm install -g netlify-cli`).

```bash
./bin/publish
```

The page is served at `https://<site-name>.netlify.app`. It lists all admitted
students with their booked slot (sorted by matricola) and pre-filled cal.com
booking links for those who haven't booked yet.

## License

Copyright (C) 2026 Massimo Santini — released under the
[GNU General Public License v3 or later](LICENSE).
