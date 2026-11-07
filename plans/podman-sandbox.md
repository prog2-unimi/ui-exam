# Run each student's gradle in a throwaway Podman container

Started 2026-11-07. `exam-pipeline compute` runs every submission's
`./gradlew clean test` and `./gradlew clean javadoc` on the host, as the
account's user (`pipeline/compute.py`), which the apps contract (`apps.md`,
*What the code provides*) forbids for strangers' code: such a step runs alone in
a throwaway container, with no network and only the directory it works on. Done
means `compute` runs those two gradle calls that way, with unchanged results
(`marks.tsv`, `computed/*.stdout`, `javadoc/`).

## Restart here

Read `src/examui/pipeline/compute.py` (the two `subprocess.run` of `./gradlew`,
with their timeouts) and `src/examui/data/extraction.py` (`spotlessApply`, which
also runs the student's overlaid build on the host). `podman` is at
`/usr/bin/podman`. Nothing is built yet; the next action is to settle the open
choices below, one at a time.

## Open

- [ ] Image: JDK and Gradle wrapper distribution plus a warmed dependency cache,
  built from a `Containerfile`; where the `Containerfile` lives (this
  repository, or the private deploy repository `apps.md` describes).
- [ ] No network means dependencies resolve offline: how the cache gets into the
  container (baked into the image, or a read-only mount), and whether the
  template project's dependencies cover every submission.
- [ ] Mounts: only the student's `source/` writable, plus the cache read-only;
  `javadoc/` and `computed/` outputs written back with the host user's ownership
  (uid 1000).
- [ ] Limits: timeout, memory, CPU and pids per container, against what
  `compute` uses now and its worker count (`os.cpu_count()` threads).
- [ ] `spotlessApply` in `extraction.py` also runs the overlaid build: in scope
  of this plan or left on the host.
- [ ] Measure first: current time per student for test and javadoc, to compare
  with the containerised run on the same cohort.

## Constraints

- Scope is the `compute` step only (`gradlew test` and `javadoc`); the diff
  feature's materialisation (`models/diff.py`) is not part of this plan.

## Watch out

- Files a rootless container writes can come out owned by a mapped uid, not the
  host user's: check ownership in `work_dir/student` after a run.
- `pygount` reads the extracted sources only and stays on the host.
