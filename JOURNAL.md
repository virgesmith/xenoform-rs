# Development Journal

A running log of every task/PR: *why* it was done and the *design decisions* made.
Newest entries at the top. This is the durable record of intent that keeps the
maintainer in control of the codebase's direction — see the
[Task & Design Summaries](AGENTS.md#task--design-summaries) policy in `AGENTS.md`.

Entry template:

```markdown
## YYYY-MM-DD — <title> (#PR)

**Why** — the motivation and the problem this solves.

**What** — high-level description of the change.

**Design decisions**
- <decision> — alternatives considered, why this was chosen.

**Follow-ups** — anything deferred, known limitations.
```

---

## 2026-07-10 — Fold the Python ABI into the module checksum (issue #13)

**Why** — A compiled extension is specific to the interpreter that built it: a
free-threaded (`3.14t`) binary is version-specific, and a GIL `abi3` binary loaded
under a free-threaded interpreter silently re-enables the GIL. Previously the
checksum only covered the generated sources, so switching interpreters left users
with a stale binary and the "delete the `ext` folder" failure mode — or worse, a
binary that imported but degraded free-threading without any signal.

**What** — Two complementary changes so an interpreter switch produces a *correct*
rebuild automatically:
1. `ModuleSpec.make_source` emits the interpreter's ABI tag as a
   `// Built for Python ABI: …` comment at the top of the generated `lib.rs`.
   Because `__checksum__` is a hash of the generated sources, the comment makes the
   freshness check ABI-sensitive, so a different Python version/GIL mode/platform
   triggers the normal rebuild.
2. Each interpreter ABI builds into its own cargo target directory
   (`target/<abi-tag>/`, via `CARGO_TARGET_DIR`), and `PYO3_PYTHON` is pinned to
   `sys.executable`.

**Design decisions**
- ABI tag source is `sysconfig.get_config_var("EXT_SUFFIX")` (e.g.
  `.cpython-314t-x86_64-linux-gnu.so`) — a single value that captures Python
  version, free-threaded flag, and platform on all OSes in the CI matrix.
  `SOABI` was rejected (historically undefined on Windows);
  `sys.implementation.cache_tag` was rejected (omits the free-threaded `t` flag,
  which lives in the ABI tag, not the bytecode cache tag).
- Embedded as a source comment rather than mixed into the hash bytes directly.
  Both make the checksum ABI-sensitive, but the comment also leaves the ABI
  human-readable in `lib.rs`, so when a stale binary is suspected the value that
  drove (or didn't drive) a rebuild can be read straight from the generated
  source. rustfmt preserves the leading comment, so it survives formatting.
- **Per-ABI target dir was the load-bearing fix.** The checksum change alone was
  insufficient and produced a hard `SystemError: init function of <mod> returned
  uninitialized object`: it correctly triggers a rebuild, but a `cargo build` in the
  *existing* target dir reuses pyo3's cached build-config (interpreter version,
  abi3, GIL mode) — cargo has no fingerprint input that changes when only the
  interpreter behind a stable venv path changes (a GIL->free-threaded `uv sync`
  keeps `.venv/bin/python` identical), so it relinks our recompiled crate against a
  stale, ABI-mismatched pyo3. Alternatives rejected: (a) `cargo clean`/wipe target
  on every rebuild — kills incremental compilation and the fast edit-compile loop,
  and heavy dep trees (polars) would recompile from scratch on every source edit;
  (b) invalidate via `PYO3_PYTHON` value change — fails here because the venv path
  is stable across the switch, so the value doesn't change. Isolating by ABI dir
  needs no fingerprint trickery: a different interpreter simply uses a different,
  empty dir and does a clean build, while switching back reuses a warm cache.
- `PYO3_PYTHON = sys.executable` pins pyo3 to the interpreter doing the import,
  rather than whatever `python` is first on `PATH` — important because running
  `.venv/bin/python` without activating the venv leaves a system `python` ahead on
  `PATH`, which pyo3 would otherwise configure against.
- `CARGO_TARGET_DIR` is resolved to an absolute path: cargo runs with
  `cwd=module_dir`, so a relative value would resolve against that and land the
  artifacts in the wrong place.

**Follow-ups** — Per-ABI target dirs multiply on-disk build artifacts (one tree per
interpreter used). The issue #13 "share a cargo target dir across modules" item
should layer on top as `extmodule_root/<abi-tag>/` — sharing across modules while
still isolating by ABI. Sidecar checksum file and AOT build command still untouched.

## Rationale for this file

**Why** — The maintainer wants to retain ownership of the codebase — understanding
every change well enough to explain and modify it independently — rather than being
outpaced by the agent. Needed explicit rules of engagement and a durable record of
intent per change.

**What** — Added a *Collaboration & Ownership* section (plan-first-with-approval,
small diffs, explain-it-back gate, justify trade-offs, learnable idioms) and a
*Task & Design Summaries* section to `AGENTS.md`, wired both into the Workflow, and
introduced this `JOURNAL.md`. Also noted in `AGENTS.md` that the `examples` extra
must be installed for `ty` to pass (it type-checks `examples/`, which imports pandas).

**Design decisions**
- Single append-only `JOURNAL.md` at the repo root — chosen over per-task files in
  `docs/tasks/`. One file is lower-friction to maintain, reads top-to-bottom as a
  history, and avoids proliferating small files. Trade-off: it will grow over time,
  but old entries can be archived if it ever gets unwieldy.

**Follow-ups** — None.
