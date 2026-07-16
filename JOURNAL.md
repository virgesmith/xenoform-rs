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

## 2026-07-16 — Drop the ABI comment from the generated source (#20)

**Why** — Follow-on cleanup to the 2026-07-10 entry below, which landed two
complementary changes for the same goal. Only one of them turned out to be load-bearing:
because `get_lib_path` resolves the binary *inside* the per-ABI target dir, the freshness
check is already ABI-partitioned — a 3.14t run reads the checksum out of
`target/cpython_314t_*/release/lib*.so` and can never see the 3.13 binary. So within any
one target dir the ABI is a constant, and folding it into the checksum decides nothing.

**What** — Removed the `// Built for Python ABI: …` comment from `_MODULE_TEMPLATE` and
the `python_abi()` call from `make_source`, leaving the generated sources ABI-independent.
`python_abi` itself stays — `python_abi_tag` (hence the target dir) is built on it.
Renamed `test_checksum_abi.py` to `test_abi.py` and replaced the embedding test with its
inverse, asserting the ABI does *not* appear in the generated source.

**Design decisions**
- Removed rather than kept for its documentation value. The comment's stated secondary
  benefit was leaving the ABI human-readable in `lib.rs` for debugging, but that is
  unsound: `lib.rs` is shared across ABIs while the binaries are not, and it is only
  rewritten when a rebuild fires. Alternate 3.13 → 3.14t → 3.13 and the third run finds a
  matching checksum, reuses its binary and never rewrites the source — leaving a 3.13
  binary loaded from a `lib.rs` stamped `314t`. It misleads at exactly the moment a stale
  binary is suspected, which was the case it existed to serve.
- Bonus: ABI-independent sources end the spurious churn where every interpreter switch
  rewrote `lib.rs`, invalidating cargo's fingerprint for our crate on both sides of the
  switch. Each ABI's tree now stays warm.
- Safe against the #13 follow-up to share a target dir across modules, since the proposed
  `extmodule_root/<abi-tag>/` layout stays partitioned by ABI. If that partitioning were
  ever removed, the checksum would have to become ABI-sensitive again.

**Follow-ups** — None; the #13 follow-ups noted below are unaffected.

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

## 2026-07-09 — Add Monte Carlo simulation example with rayon parallelism (#18)

**Why** — Item 2 of #16: the existing examples don't showcase rust's biggest wins —
tight RNG loops that numpy can only vectorise at the cost of materialising the whole
simulation in memory — nor multi-core scaling, which rust gets via `rayon`
regardless of the GIL.

**What** — Added `examples/monte_carlo.py`, a parallel-only comparison pricing an
arithmetic-average Asian call option two ways: vectorised numpy sharded across a
thread pool, and rayon-parallel inline rust, with a timing table up to a million
paths. Also the first example to use third-party crates (`rand`, `rand_distr`,
`rayon`) and a cargo feature flag (`small_rng`). README gained a matching *Monte
Carlo simulation* section; CI runs the new example.

**Design decisions**
- *Asian option rather than European or π-estimation* — a European option needs only
  one normal draw per path, so numpy vectorises it trivially and there is no loop
  story to tell. The arithmetic-average payoff needs the whole path, giving the
  per-step sequential loop rust excels at while still admitting a vectorised numpy
  baseline for an honest comparison.
- *No pure-python baseline* — nobody would run a Monte Carlo like this without numpy,
  so the naive-loop column (~60× slower than numpy) added length, CI time, and a
  strawman without informing the comparison. numpy is the realistic contender.
- *In-place numpy operations* — the natural expression chains `standard_normal`,
  `cumsum` and `exp`, each allocating its own `(n_paths, n_steps)` array (~2GB each
  at a million paths), which would exhaust the 7GB macOS CI runners. In-place ops
  bound peak memory at one matrix, and also make the baseline as strong as numpy can
  reasonably be — the point is that rust streams each path with no allocation at all.
- *Parallel-only comparison* (per maintainer review, in two steps) — the original
  four-way table (single- and multi-threaded variants of both numpy and rust) buried
  the point. Comparing 1-core numpy against 22-core rayon conflated rust's per-core
  advantage with core count, so a threaded numpy baseline was added; the
  single-threaded columns were then dropped entirely as the existing examples already
  cover the per-core story. numpy ufuncs are single-threaded, so the multi-core numpy
  version shards paths across a `ThreadPoolExecutor`, one independent RNG stream per
  shard via `SeedSequence.spawn` (the numpy-recommended way to get parallel streams).
  It is memory-bandwidth-bound — every thread streams its share of the 2GB matrix
  through RAM, so scaling plateaus at ~8× on 22 cores — while rayon holds each path in
  a register and stays ~2.7× ahead at scale.
- *3.14t is not load-bearing for this example* (found empirically by the maintainer,
  who measured near-identical speedups on 3.13 and 3.14t — corroborated: 1M paths gives
  numpy+threads ~546ms / rayon ~228ms on GIL 3.13 vs ~566/219 on 3.14t). Both sides
  already bypass the GIL: rayon runs the whole loop in compiled code with the GIL
  released, and numpy releases the GIL inside each large ufunc, holding it only for the
  negligible glue between array ops. Free-threading would only help a *pure-python*
  threaded loop, which we don't have. The README and docstrings were corrected to drop
  the implication that 3.14t drives the result; the table is now labelled 3.13. The
  issue's "pairs especially well with 3.14t" framing turned out not to hold once the
  python baseline is numpy rather than pure python.
- *`SmallRng` (Xoshiro256PlusPlus on 64-bit, via the `small_rng` cargo feature) over
  `StdRng`* — RNG speed dominates the inner loop and cryptographic quality is
  irrelevant here; it also demonstrates passing `features=` through `rust_dependency`.
- *One independently-seeded RNG per path in the rayon version* (`SmallRng::seed_from_u64(seed + i)`)
  — keeps the result deterministic regardless of thread scheduling. The per-path seeds
  are consecutive integers, which differ in only a bit or two; `seed_from_u64` scrambles
  each one into the generator's full 256-bit state with the SplitMix64 finalizer (the
  seeding step, distinct from Xoshiro256PlusPlus itself, which then produces the draws),
  so adjacent paths get statistically independent streams — the seeding scheme the
  xoshiro authors recommend. The alternative, `map_init` with one RNG per rayon worker,
  is slightly faster but nondeterministic. Both implementations are consequently
  reproducible — pinning the draws to the path/shard index (rather than to the thread)
  means the result is independent of thread scheduling, with no data races. numpy's is
  bit-deterministic by construction (fixed shard sizes, `SeedSequence.spawn` order,
  ordered reduction); rayon's is bit-stable in practice, the only theoretical wobble
  being FP-reassociation in the parallel `.sum()`, which is not a race.
- *Top size capped at a million paths* — the numpy baseline must materialise the whole
  `(n_paths, n_steps)` matrix; at a million paths that peaks at ~2GB (measured), and
  the sharded threads hold it all at once. 3M paths (~6GB) was tried but would OOM the
  7GB macOS CI runners on which the example runs, so the table stops at 1M.
- *`perf_counter` instead of the other examples' `process_time`* — `process_time`
  sums CPU time across threads, which would show rayon as no faster than
  single-threaded rust; wall-clock time is the honest metric for a parallelism demo.
- *Statistical rather than exact result check* — each implementation consumes a
  different RNG stream, so estimates agree only within Monte Carlo error; the assert
  bounds the spread at ~6 standard errors (payoff σ ≈ 9 for the chosen parameters).
- *Warm-up calls before timing* — the one-off module import/hash-check cost (~350 ms)
  otherwise lands on the first timed rust call and misrepresents per-call cost.

**Follow-ups** — Items 1, 3 and 4 of #16 (Mandelbrot, Levenshtein, n-body) remain. A
future example with a genuinely GIL-bound python baseline (pure-python threading) would
actually demonstrate the 3.14t benefit this one does not.
While developing, single-threaded rust (a variant since removed from the example)
measured ~30% slower under 3.14t than under GIL 3.13 (~2.0s vs ~1.5s at a million
paths, consistent across runs) — unexplained, may merit investigation.

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
