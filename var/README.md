# Runtime State

`var/` is reserved for software runtime state that should not live in the repository root:

- `var/state/`: SQLite state, job-scoped run directories, and job logs.
- `var/reports/`: exported HTML reports.

Committed research baseline artifacts still live under `outputs/`. New ad hoc software state should go under `var/`.
