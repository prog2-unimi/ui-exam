# examui

A Flask web application for assisting oral exam sessions in the
[Programmazione II](https://prog2.di.unimi.it) course at Università degli Studi di Milano.

Given a student's submitted source code and generated Javadoc, it provides:

- a searchable history of all past exam events per student;
- a per-session oral page with a note editor, syntax-highlighted source navigator
  (with symbol search and Javadoc deep-links), and a dependency graph of the
  student's classes (topologically ordered, transitively reduced).

> **Note:** This is preliminary software, developed for personal use during exam
> sessions. Interfaces and data formats may change without notice.

## Usage

Copy `.envrc.example` to `.envrc`, fill in the paths, then:

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

## License

Copyright (C) 2026 Massimo Santini — released under the
[GNU General Public License v3 or later](LICENSE).
