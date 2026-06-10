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

```
direnv allow   # or source .envrc manually
./run.sh
```

The app listens on `127.0.0.1:8765`. Reach it from a tablet via an SSH tunnel.

## License

Copyright (C) 2026 Massimo Santini — released under the
[GNU General Public License v3 or later](LICENSE).
