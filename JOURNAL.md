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

## 2026-10-18 — Cheaper up-to-date check: a checksum file per ABI (#13)

**Why** — To decide whether a module was up to date, `_get_module_checksum` started a Python subprocess, loaded the
extension in it and printed `__checksum__`. It had to be a subprocess, because a loaded extension can't be unloaded or
reloaded, so loading it in-process would stop a rebuild from ever being picked up. That cost about 12 ms per module
on every import (Linux; Python starts more slowly on macOS and Windows).

**What**
- After a successful build, the hash is written to a checksum file in the module folder, named after the interpreter
  ABI: `ext/mod_ext/cpython_314_x86_64_linux_gnu_so.checksum` (`get_checksum_path(module_dir)` in utils.py, using
  `python_abi_tag()`, the same name as the target dir). `_read_checksum` replaces `_get_module_checksum` and
  `_CHECKSUM_SCRIPT`.
- A module is up to date when the library exists, the generated `src/lib.rs` exists, and the checksum file holds the
  current hash. Otherwise it's rebuilt.
- A rebuild deletes the checksum file before writing the sources and running cargo, and writes it only once the build
  has succeeded and the library exists.
- `__checksum__` stays in the generated module so it can be inspected, but nothing checks it at runtime.
- New `test_checksum.py`: a build writes the checksum and a second check reuses the build; a missing or stale checksum
  rebuilds; another ABI's checksum is ignored; deleting the module folder or just `src/` rebuilds; a checksum without
  its library isn't trusted; a failed build leaves no checksum. Two tests that faked a stale module now patch
  `_read_checksum`.
- README and SKILL.md describe the checksum files (SKILL.md also no longer says the hash includes the ABI, which
  stopped being true on 2026-07-16). Existing ext folders have no checksum files, so their modules are rebuilt once.
- Measured (Linux, 3.14, warm): the check takes **~12 ms → ~5.5 µs** per module, and the existing 167 tests take
  **2.66 s → 2.17 s**.

**Design decisions**
- *In the module folder, one file per ABI.* The module folder is where a user looks for a module's generated files,
  and deleting it then deletes the checksums, which forces a rebuild. The first version put the file next to the
  binary in `ext/target/<abi>/release/`, where deleting the module folder left a matching checksum behind, so the
  module loaded from an empty folder. A single `.checksum` in the module folder (the issue's suggestion) was rejected:
  the folder is shared by every interpreter, but each has its own binary, so a 3.14 → 3.14t switch would find a
  matching hash and load the wrong binary, or none. It's the trap the 2026-07-16 entry describes for the ABI comment
  in `lib.rs`. Naming the file after the ABI gives both.
- *`src/lib.rs` must exist too*, although loading doesn't need it. Diagnostics (`CompilationError`, `RustWarning`,
  `build.log`) refer to its line numbers, and deleting just `src/` should also force a rebuild. Since the shared target
  dir (2026-10-18), the binary no longer lives in the module folder, so without this check a deleted folder was never
  refilled. That was true of the subprocess check as well.
- *Invalidate, build, then stamp.* If the old checksum survived a rebuild that didn't complete (the build failed, the
  process was killed, the stamp couldn't be written), it could vouch for a binary that wasn't built from the sources
  it names, e.g. after the sources were changed back. Deleting it first means a checksum only ever exists for a
  completed build. Within xenoform's own flow, the checksum and the binary can't get out of step.
- *The stamp is written before `_warn`*, so turning `RustWarning` into an error doesn't stop the build being
  recorded. The build did succeed, and an up-to-date module skipping its warnings is the existing behaviour.
- *No atomic write.* A partly written file holds a truncated hash, which can't equal a full one, so the worst case is
  a rebuild.
- *No fallback to the subprocess check when there's no checksum file.* It would keep the slow path, and its tests,
  around forever. The cost is one rebuild of existing modules, which is cheap: cargo's dependency cache is still warm.
- Rejected: *searching the binary's bytes for the expected hash* (the `const &str` is stored verbatim, and it took
  ~0.04 ms with `mmap`). It keeps the binary as the only source of truth, but relies on how rustc lays out string
  literals on every platform. Maintainer decision: use a checksum file.
- Rejected: *storing the binary's size and mtime with the hash* to catch a binary changed outside xenoform (a manual
  `cargo build` after hand-editing `lib.rs`, a partly restored `ext/`). Maintainer decision: hash only, since a normal
  edit can't cause this.
- Rejected: *checking the loaded module's `__checksum__` against the hash.* A mismatch can only come from outside
  changes, and when it's found the module is already loaded, so it couldn't be rebuilt in-process anyway.

**Follow-ups**
- Known limitation: anything that rewrites the binary without going through xenoform-rs leaves the checksum
  describing the old build. That includes a manual `cargo build`, copying binaries, and building the same module with
  an older xenoform-rs that doesn't know about checksum files. Deleting the checksum file (or the module folder)
  forces a rebuild.
- `test_module_reused_when_up_to_date` is still skipped on Windows because "re-checking a loaded module rebuilds".
  That was probably the subprocess check failing there, which would have meant every Windows import rebuilt. The
  check no longer loads anything, so the skip can likely go, but that needs Windows CI to confirm.
- Build locking (#13) should cover the whole read, build and stamp sequence.

---

## 2026-10-18 — Share one cargo target dir across modules (#13)

**Why** — Each `<module>_ext` folder had its own cargo target dir, so pyo3 and every other dependency was compiled
again for each module: a cold compile per module and hundreds of MB of duplicate artifacts. #13 rated this the most
valuable item, and the 2026-07-10 ABI entry left it as a follow-up.

**What**
- `get_target_dir(extmodule_root)` returns `extmodule_root/target/<abi-tag>/`, and `get_lib_path(extmodule_root,
  module_name)` looks for the library there. Each module folder keeps its own `Cargo.toml`, `Cargo.lock`, `src/` and
  `build.log`, and cargo still runs in it.
- `_get_cargo_env` no longer needs the module dir.
- New `test_target_dir.py`: two modules build into the shared `release/` dir, and neither gets a `target/` of its
  own. Existing tests are updated for the new signatures.
- README and SKILL.md describe the new layout, and say that old per-module `target/` folders can be deleted.
- Measured (cold run of the full test suite, Linux, 3.14, 35 modules): **225 s → 27 s**, and `ext/` **2.1 GB → 146 MB**.
- Separately, dev tooling is bumped: the pre-commit hooks (uv 0.13.1, ruff v0.17.1, ty v0.0.89) and the dev
  dependencies in `uv.lock`.

**Design decisions**
- *Pointing several crates at one target dir is safe.* Cargo supports it: each dependency build is keyed by a hash of
  its version, features, profile and `RUSTFLAGS`. Modules with different `profile=` overrides or crate features get
  separate copies of the affected dependencies, so sharing is reduced but nothing goes wrong. Final artifacts can't
  collide: the package name is `module_name`, and the module folder is `module_name + "_ext"`, so two folders under
  one root always have different package names.
- *Still one directory per ABI*, which keeps the GIL → free-threaded protection from 2026-07-10. Sharing is across
  modules, never across interpreters.
- *`extmodule_root/target/<abi>` rather than `extmodule_root/<abi>`* (the layout the 2026-07-10 follow-up proposed).
  It follows cargo's naming, is obvious when browsing `ext/`, and can't collide with a module folder, since those all
  end in `_ext`.
- *The root is passed explicitly* to `get_target_dir`/`get_lib_path`. Rejected: reading `get_config()` inside them,
  which would give `compile.py` two sources for the root (its import-time `extmodule_root` and the live config) that
  could disagree. Also rejected: deriving it from `module_dir.parent`, which ties the two paths together without
  saying so. The cost is that the first argument now means "root" rather than "module dir". Only internal code and
  tests call these (neither is exported), and a wrong argument gives "library not found", not a stale load.
- *Old per-module `target/` dirs aren't deleted automatically.* The library would be deleting files on the user's
  disk without asking, Windows may lock them, and the extra code would need tests for very little gain. The docs say
  they can be deleted.
- *Concurrent builds are now serialised.* Cargo locks the target dir, so two processes building different modules
  (e.g. pytest-xdist) take turns instead of building in parallel. This is safe, and it doesn't replace the #13
  build-locking item, which is about writes to `lib.rs`/`Cargo.toml` within one module's folder.

**Follow-ups**
- The fixed 300 s build timeout now includes any wait for cargo's target-dir lock. Another #13 item makes the timeout
  configurable.
- `extmodule_root` is still read once, at import, in `compile.py` (a separate #13 item). Reading it at each use site
  would be a natural small next PR.

---

## 2026-10-14 — Issue rustc warnings as `RustWarning` (#32, item 1)

**Why** — rustc warnings (unused variables, unnecessary `mut`, dead assignments) were parsed after every build but only
written to `build.log`, which users rarely read. They're often real mistakes or non-idiomatic habits. This is also the
channel clippy lints will use (#32, item 2).

**What**
- `RustWarning(UserWarning)` in `errors.py`, exported from the package. It carries the `RustDiagnostic` as
  `.diagnostic`.
- After a successful build, `_warn` (compile.py) issues one `RustWarning` per warning-level diagnostic, shortened with
  `_brief` and prefixed `rustc warning in module '<ext_name>':`.
- Tests: a warning is issued with its diagnostic and attributed to the caller, a clean build issues none, and a filter
  can make it an error. `test_rebuild_when_outdated` ignores the unused-import warning its unused `fibonacci.rs` causes.
- README documents the warnings and how to filter them.

**Design decisions**
- *A warnings category, not `logger.warning`.* Users can silence or escalate warnings with Python's own filters (e.g.
  pytest `filterwarnings` in CI) without any new config.
- *The diagnostic is attached to the warning instance* (`warnings.warn(RustWarning(msg, d))`), so code using
  `catch_warnings(record=True)` gets the structured data, as with `CompilationError.diagnostics`. Rejected: a plain
  string message, which callers would have to parse.
- *Attributed with `skip_file_prefixes`* (Python 3.12+) to the first frame outside the package, i.e. the call that
  triggered the build. This is more robust than a `stacklevel`, which depends on the call path. Rejected: attributing to
  the decorated function's definition. A crate can hold functions from several Python files (`module_name=`), and until
  #26's span-to-docstring mapping exists we can't tell which function a warning belongs to.
- *Only on successful builds.* On failure the `CompilationError` matters, and warnings alongside it would bury it. They
  remain in `build.log`.
- *One warning per diagnostic, with no `_select`-style cap*, so individual lints can be filtered by message.
- *Command-line filters match on the message.* The issue suggested `-W error::xenoform_rs.RustWarning`, but CPython
  won't import a third-party module to resolve a `-W`/`PYTHONWARNINGS` category ("Invalid -W option ignored: invalid
  module name"). `PYTHONWARNINGS="error:rustc warning"` works, which is why the message prefix is fixed. In-process
  filters and pytest config can use the category.

**Follow-ups**
- Warnings only appear when the module is rebuilt. An up-to-date module skips cargo, so they aren't repeated.
- Lines in the message refer to the generated `src/lib.rs`, until #26's line mapping exists.
- The test suite could set `filterwarnings = ["error::xenoform_rs.RustWarning"]` to catch generated code that starts
  warning.
- #32 item 2 (opt-in clippy) will reuse this channel.

---

## 2026-10-13 — Constants by name: `constants=["MAGIC_NUMBER", "BIG: u64"]`

**Why** — `constants={"BIG": rust_constant(BIG, "u64")}` was clunky. Every name was written twice, overriding the type
needed an extra import and a wrapper call, and the README needed a long box to justify the syntax.

**What**
- `constants` is now `list[str]`. Each entry is `"NAME"` or `"NAME: rust_type"`. The value is looked up by name where
  the decorator is applied: first the caller frame's locals (function locals, or the class body for methods), then its
  globals (module-level and imported names). The rust name is always the python name.
- `rust_constant` and `RustConstant` are removed. `translate_constant(name, value, rust_type=None)` takes the type
  directly. `_parse_constant` (compile.py) splits and validates an entry. An unknown name, an invalid name or a missing
  type after the `:` raises `RustConfigError` at decoration time.
- Tests cover imported, class-body and local constants, a local shadowing a global, entry parsing, and unknown names.
  The conflict test now gets two definitions by reassigning a local between decorations.

**Design decisions**
- *Supersedes "a dict of values, not a list of names" (the 2026-10-12 constants entry).* That entry rejected names
  because `func.__globals__` can't see locals or class attributes. Reading the caller's frame (`sys._getframe(1)` in
  the decorator) sees exactly the scope the decorator is written in, so both work. Imported names were never a
  problem: an import binds a global. The other objection, typos, was weak. An unknown name now fails at decoration
  time, where a typo in a dict key only failed in rustc.
- *Frame inspection is unusual Python.* It's confined to one line in `rust()`, the frame isn't stored, and the frame is
  always our own direct caller on the same thread, so free-threading isn't a concern. The alternative,
  `func.__globals__` plus `inspect.getclosurevars`, would still miss class bodies, and closure variables only include
  names the function body uses, while the rust body (a docstring) uses none.
- *No dict form kept for renames or computed values* (maintainer decision: "if there's a name clash then tough").
  One form is simpler to document and test. A computed value is assigned to a variable first.
- *The type goes in the entry, as in rust (`"BIG: u64"`).* This reads like the generated `const BIG: u64`, needs no
  import, and keeps the type next to the name, so an imported constant can't lose it. The previous entry's reasons for
  not reading `Annotated` annotations still hold. The entry is split on the first `:`. A name can't contain one, so
  paths such as `std::primitive::u64` survive.
- *Locals shadow globals* (`ChainMap(f_locals, f_globals)`), as in normal python name resolution.

**Follow-ups**
- A variable from an enclosing function is only visible if the decorating scope also uses it (it's only then a free
  variable in `f_locals`). Documented in the README, not worked around.
- Dotted names (`"other_module.CONST"`) aren't supported: they fail name validation. Rejected for now: mangling to
  `other_module_CONST` invents a name that appears nowhere in python, and `from other_module import CONST` already
  works. Mirroring the path as rust `other_module::CONST` would be explicit, but would need nested `mod` generation
  and could collide with `modules=`.
- Linters can't see names inside strings, so an import used only by `constants` is flagged F401, and the pre-commit
  `ruff-check --fix` would delete it. The constant then fails loudly (`not found`), not silently. Documented in the
  README (`# noqa: F401`). It's the main cost of names over values; revisit if it proves a nuisance in practice.
- Enum members still aren't supported: `type(X.A)` is `X`, which has no mapping, and with an explicit type the value
  renders as `X.A`, which isn't valid rust. Proposed: an `Enum` class in `constants` becomes
  `mod X { pub const A: ... }`, so `X.A` is `X::A` in rust, with members' `.value` taken automatically. Also, the
  "no override provided" error points at `Annotated`, which constants ignore; for constants it should suggest
  `"NAME: <rust type>"`.

---

## 2026-10-12 — Default mappings for the remaining numpy integer widths

**Why** — beahiv's `decode_batch` kernel returns a `uint8` array. Even with a rust override on the whole return
tuple, every element type must have a default mapping (see Follow-ups), and `np.uint8` had none.

**What** — `DEFAULT_TYPE_MAPPING` gains `np.int8`/`np.int16` → `i8`/`i16` and `np.uint8`…`np.uint64` → `u8`…`u64`.
Covered by `test_translate_constant` cases, which go through `translate_type`. The README and skill mapping tables are
updated. `np.float16` replaces `np.uint8` as the unsupported example.

**Follow-ups** — An override doesn't stop `RustTypeTree` translating the subtypes of the overridden type
(extension_types.py, `__init__`), so an override can't yet stand in for an unmapped *inner* type. Skipping subtypes
when `override` is set would make it a real escape hatch, but needs checking against everything that reads `subtypes`.

---

## 2026-10-12 — Explicit constant types via `rust_constant`; annotations no longer read

**Why** — The first downstream use (beahiv's `encode_batch`) imported its constants from another module
(`from .cell_id import Q_OFFSET`) and annotated them there as `Annotated[int, "i64"]`. Those annotations were never
seen: an annotation is stored in the declaring module's `__annotations__`, not on the value, and the import binds only
the value. The constants silently became `i32`, still compiled, and needed `as i64` casts in the rust body. This is the
"silently drops the override" risk recorded in the entry below, hit on the first real use.

**What**
- New public `rust_constant(value, rust_type: str) -> RustConstant` (utils.py, exported with `RustConstant`).
  `constants={"Q_OFFSET": rust_constant(Q_OFFSET, "i64")}` gives `const Q_OFFSET: i64 = ...;`. A bare value is typed
  from `type(value)` as before. A non-string `rust_type` raises `RustConfigError`.
- Removed the annotation lookup: `_translate_constants` no longer takes `func`, and the `annotationlib`/`FORWARDREF`
  reading, the `eval` of string annotations, the `Final` unwrapping and the 3.13 `pragma: no cover` branch are gone.
  `translate_constant(name, value)` unwraps a `RustConstant` itself.
- Tests: `test_annotations_are_ignored` pins the new behaviour, using a constant imported from `other_module` that is
  annotated there. The `Annotated`/`Final` cases became `rust_constant` cases.
- README "Constants" has an IMPORTANT box explaining why it isn't `Annotated`. AGENTS.md records constants as the one
  exception to "`Annotated` is the escape hatch". The skill lists the `constants` parameter, which it had omitted.

**Design decisions**
- *Supersedes "the override is read from the python variable's annotation" below.* That was chosen for syntax that
  matches arguments. But an argument's annotation is part of the function signature, so it is always available. A
  constant's annotation is only found if the variable was declared, under the same name, in the decorated function's
  own module. Imported, computed, local and renamed constants all lose it, without an error. An explicit type that can't
  get lost is worth the less "natural" syntax.
- *Removed, not kept alongside.* Keeping the lookup as a fallback would leave two ways to type a constant, and the
  silent failure for any annotated constant that's imported. The feature is unreleased (only on `module-constants`,
  after v0.1.6), so removing it breaks nobody.
- *Following the import was rejected.* Parsing the module for `from m import NAME` and reading `m.__annotations__` is
  possible, but misses `import m; m.NAME`, aliases, re-exports through `__init__`, and computed values.
- *A wrapper, not a `(value, type)` tuple.* A tuple is already a valid constant value (`(1, 2.5)` → `(i32, f64)`), so
  `(5, "i64")` would be ambiguous.
- *`rust_type` is a rust type string, not a python type run through `translate_type`.* Accepting `Annotated[...]` here
  would bring back the syntax this removes, and anyone wanting a non-default type already knows the rust spelling.
  Passing a python type by mistake raises, rather than being stringified into nonsense rust.

**Follow-ups** — A shared constant's type is now repeated at each `rust_constant` call site. Sharing one `constants`
dict across functions (as beahiv does) avoids that.

---

## 2026-10-12 — Module-level constants via `@rust(constants=...)`

**Why** — Rust code had no access to constants defined in Python. The rust body is the docstring, and an f-string is
never a docstring, so the only option was to retype the value in rust, which duplicates it.

**What**
- `@rust` has a new `constants: dict[str, Any] | None` parameter. Each entry is rendered as `const NAME: TYPE = VALUE;`
  by `translate_constant` (utils.py) and added to a new `ModuleSpec.constants: set[str]`. `make_source` emits the set,
  sorted, at module level before the functions.
- The rust type is translated by `translate_type` from the annotation of the module-level python variable with the
  same name as the key, if there is one, otherwise from `type(value)`. So `BIG: Annotated[int, "u64"] = 2**40` gives
  `const BIG: u64 = ...`. A `Final` qualifier is unwrapped (bare `Final` falls back to the value's type).
- Constant names must be identifiers and not Rust keywords (`RustConfigError`). A type with no mapping and no override
  raises the usual `RustTypeError`.
- `_translate_value` now renders non-finite floats as `f64::NAN`/`f64::INFINITY`/`f64::NEG_INFINITY`, since python's
  `nan`/`inf` aren't rust literals. This also fixes `inf`/`nan` default argument values, which previously produced
  uncompilable rust.

**Design decisions**
- *A parameter on `@rust`, not a separate decorator.* There is no function to decorate for a constant. A stacked
  decorator would also be order-dependent and have to stash data on the function object. A parameter follows
  `dependencies`/`imports`/`modules`, and the constants always arrive in the same `add_function` call as their
  function, so they can't miss a build.
- *Module scope, not function scope.* Function-local `const` items would have avoided cross-function coupling and
  conflicts. Module scope was chosen so that a constant can be declared once and shared, at the cost that a function
  may silently rely on a constant declared by another. Accepted.
- *A set of rendered items, with conflicts left to rustc.* Identical declarations from several functions collapse in
  the set. Different values for the same name produce two items, which rustc rejects with E0428, surfaced by
  `CompilationError`. A dict with a Python-side check (like `_append_profile`) would report the conflict at decoration
  time with both values named. Rejected as extra code for a rare case whose rustc message is already clear.
- *A dict of values, not a list of names.* `constants=["MAGIC_NUMBER"]` resolved via `func.__globals__` is shorter,
  but can't see locals or class attributes, and a typo only shows up when the decorator runs. A dict is explicit and
  allows a computed value or a different rust name.
- *Types go through the usual mechanism, so `Annotated` overrides work.* A first version had its own table of
  supported constant types, which couldn't express e.g. a `u64`. Using `translate_type` means an `int` constant is
  `i32` like an `int` argument (so `n + MAGIC_NUMBER` compiles), numpy scalars choose widths as for arguments, and
  overrides reach anything else, e.g. `Annotated[list[int], "[i32; 3]"]`, since python's `[1, 2, 3]` is also a rust
  array literal. The cost is that a value whose default mapping isn't const-constructible (an unannotated `list`,
  `bytes`, `complex`) fails in rustc rather than in python.
- *The override is read from the python variable's annotation, not passed in the dict.* This mirrors how arguments
  are typed. The alternative, an optional `(type, value)` pair in the dict, is explicit and works for computed values
  and locals. The annotation is matched by key name, so renaming the key, or passing a computed value or a local,
  silently drops the override. If the default type still compiles, the width changes without an error. Accepted for
  the more natural syntax; documented in the README.
- *`str` → `&str` is a constants-only special case.* AGENTS.md prefers overrides to special cases, but the default
  mapping (`String`) can never be built in a const, so without it every string constant would need
  `Annotated[str, "&str"]`. It only applies when there's no override.
- *Only the needed annotations are evaluated.* The decorator runs mid-import, and annotations of variables defined so
  far are visible on 3.13–3.15. But on 3.14+ (lazy annotations, PEP 649), evaluating them all raises `NameError` if
  any *unrelated* earlier annotation refers to a name defined later. So 3.14+ reads them with
  `annotationlib.Format.FORWARDREF`. String annotations (`from __future__ import annotations`, or quoted) are then
  `eval`ed individually in the module's namespace, as `typing.get_type_hints` does. 3.13 evaluates module annotations
  eagerly, so `inspect.get_annotations` can't raise there; that branch is `pragma: no cover` because coverage runs on
  3.14, and it goes when 3.13 support is dropped. Annotations are only read when `constants` is given, so existing
  code can't be affected.
- *No change-detection change.* The constants are part of `lib.rs`, which the hash already covers.

**Follow-ups**
- The 3.14+ case of an unrelated forward reference is verified manually but not by a test: an unquoted forward
  reference is a `NameError` at import time on 3.13, so it can't live in a test module run on every version.
- Values are rendered with `str()`, so containers only work where python's repr is also rust syntax (numeric
  lists/tuples). Containers of strings, for example, don't.
- Enum members aren't supported directly; pass `.value` (e.g. `{"A": X.A.value}`).
- Values are captured at decoration time; reassigning the python variable afterwards has no effect (documented).
- An unused constant produces a `dead_code` warning in `build.log`.

---

## 2026-10-10 — Stop compiled modules replacing their Python module in `sys.modules`

**Why** — Re-running `from helper import f` after `f` had been called failed with
`ImportError: cannot import name 'f' from 'helper' (.../libhelper.so)`. This was first noticed as a notebook quirk
(re-running an import cell), but scripts are affected too. The default rust module name is the defining file's stem,
and the compiled module was registered as `sys.modules[module_name]`. So it replaced the Python module of the same
name, and later imports found the extension, which only has the `_`-prefixed functions. A file such as `utils.py`
would also replace any other module registered under that name.

**What**
- The compiled module is loaded as `<module_name>_ext.<module_name>` (e.g. `helper_ext.helper`), the same name as
  its build folder and log messages, so it no longer collides with the Python module.
- `test_reimport.py` reproduces the bug with a top-level module (the case that collides) and checks that the
  Python module is left in place.
- README gains a short *Notebooks* section, which comes from the same notebook investigation. Cells defining
  `@rust` functions need a `module_name` override, and changes to `@rust` functions need a kernel restart. Both
  rules were checked in a real Jupyter kernel. The section is deliberately just the two rules rather than a list of
  failure modes: edits after a call are silently ignored, edits before a call give E0428, and new functions give
  `AttributeError`. All of these are fixed by the same restart, so users don't need to tell them apart.

**Design decisions**
- *A namespaced key, not a renamed Rust module.* For single-phase init, Python looks for the extension's init
  function using the last part of a dotted name (`PyInit_helper`), so nothing on the Rust side changes: generated
  source, symbols, library names and existing builds all stay as they are. Renaming the module (e.g. `helper_rs`)
  would have invalidated every build, and would still collide when a user's `module_name` matched their file name.
- *Keep the `sys.modules` registration.* Registering a module before running it is the standard import protocol.
  The problem was only the key.
- *The fix is at xenoform's call site, not in `load_rust_module`.* `load_rust_module` is public API for loading
  modules built some other way, and its callers choose the name.
- *No call-time cost.* The name is only used when the module is first loaded. Calls go through the `lru_cache`d
  `_get_function`, which returns the function object directly. Measured: ~200 ns per call before and after.
- `test_nested.py` loads the same library again under the bare name. pyo3 0.29 initialises a second, separate
  module object for that, which works, so the test is unchanged.

**Follow-ups**
- Checked locally on GIL 3.14 only. Free-threaded 3.14t and 3.15, where pyo3 uses the PEP 793 module export API,
  are covered by CI.

---

## 2026-10-10 — Support Python 3.13–3.15; bump CI actions and dev tooling

**Why** — Python 3.15 has been released, and the project supports only the three latest minor versions. So 3.15
comes in and 3.12 goes out. The GitHub Actions and pre-commit tools were also behind.

**What**
- `requires-python = ">=3.13"`. The classifiers and CI matrix are now 3.13, 3.14, 3.14t, 3.15, and the generated
  `Cargo.toml` uses pyo3's `abi3-py313`.
- `actions/checkout` v6 → v7, `astral-sh/setup-uv` v7 → v10.3.0. Pre-commit: uv 0.13.0, ruff v0.17.0, ty v0.0.86.
  `uv_build` bound `<0.14.0`. Relocked.
- AGENTS.md now states the three-version policy, lists everything a version bump must keep in step, and allows
  features of the oldest supported version.
- Removed the 3.12 shim in `test_freethreaded.py`: `sys._is_gil_enabled` exists from 3.13.
- `compile.py` now uses PEP 695 type parameters throughout. The module-level `P = ParamSpec("P")` and
  `R = TypeVar("R")` are gone, `rust` is declared as `rust[**P, R]`, and `_get_function` returns
  `Callable[..., Any]`, since it previously named `P` and `R` with nothing to bind them.

**Design decisions**
- *The policy is written down, not just applied.* With it in AGENTS.md, the next bump is mechanical: one PR, one
  checklist of places to change.
- *setup-uv is pinned to an exact version.* From v8, setup-uv stopped publishing major/minor tags, as a guard against
  supply-chain attacks, so `@v10` doesn't exist. checkout still publishes `@v7`, so it keeps the major-version pin.
- *None of the actions' breaking changes apply.* checkout v7 blocks fork checkouts on `pull_request_target` and
  `workflow_run`. setup-uv v8 removed the old manifest format, v9 turned cache pruning off by default (larger cache,
  no behaviour change), and v10 disables auto-caching on `pull_request_target`, `workflow_run` and `release`. The
  workflows use none of these.
- *`rust[**P, R]` with a `Callable` return, not a generic `Protocol`.* `P` and `R` appear only in the returned
  callable, so a checker could bind them at the `rust(...)` call, where there is nothing to infer them from. The
  standard fix is a `Protocol` whose `__call__` is generic. But a probe showed `ty` already moves `P` and `R` onto
  the returned callable: a decorated `def f(x: int, y: str) -> float` keeps exactly that signature, as before. So
  the direct translation was kept, and the Protocol pattern wasn't needed.
- *Few 3.13 features apply.* `TypeIs`, TypeVar defaults, `warnings.deprecated`, `copy.replace` and `ReadOnly` have
  no use site yet (no type-narrowing predicates, generic classes, deprecations, dataclass copies or TypedDicts).
  They shouldn't be forced in.
- *A single `all-checks` job is the only required status check.* The `lock-main` ruleset listed nine matrix jobs
  by name (`build (3.12, macos-latest)` …). Removing 3.12 left three required checks that would never report, and
  the PR sat with them showing as queued. The list was also already incomplete: 3.14/macos and 3.14t/ubuntu and
  windows weren't required, and 3.15 wasn't there either. `all-checks` `needs: build` and succeeds only if the
  whole matrix did, so future matrix changes don't touch the ruleset. It runs with `if: always()`, because GitHub
  counts a skipped required check as passing, so without it a failed matrix would skip this job and let the PR
  merge.
  - *Rejected: keeping per-job checks and updating the list.* It's the same chore on every version bump, and
    forgetting it blocks the PR, as happened here.
- *Rejected: adding 3.15t to CI.* Free-threading stays covered by 3.14t only, which keeps the matrix size unchanged.

**Follow-ups**
- Since each interpreter builds its own extension, abi3's one-binary-for-many-Pythons benefit may not be used,
  while it restricts pyo3 to the limited API. Whether to drop abi3 needs its own look, including the
  free-threading implications.

---

## 2026-10-10 — pyo3 and numpy crates 0.29, rayon 1.12

**Why** — The `numpy` crate 0.29 and `rayon` 1.12 have been released, and the examples, tests and docs should use
the current versions. numpy 0.29 requires `pyo3 ^0.29`, so the bump can't be made on its own.

**What**
- The default (and only supported) pyo3 version, `XenoformRsConfig.pyo3_version`, is now 0.29. It was 0.28.
- `numpy` 0.28 → 0.29 in the examples, `test_numpy.py`, `test_slice.py`, README and SKILL.md.
- `rayon` 1.11 → 1.12 in `distance_matrix.py`, `monte_carlo.py` and README.
- The README and SKILL.md "only supported version" text says 0.29. The `rust_dependency` formatting test in
  `test_utils.py` uses current strings: numpy/pyo3 0.29 and `abi3-py313`.

**Design decisions**
- *pyo3 is bumped with numpy, not left behind.* The generated `Cargo.toml` always depends on pyo3 at the configured
  version, and pyo3-ffi declares `links = "python"`. Cargo allows only one such package per build, so numpy 0.29
  with pyo3 0.28 fails dependency resolution, even before compilation. Users who need numpy 0.29 must be on pyo3
  0.29. With 0.29 as the default, that works without the `XENOFORM_RS_PYO3_VERSION` override.
- *Breaking-change check.* Before changing the default, the suite was run with `XENOFORM_RS_PYO3_VERSION=0.29`.
  Everything passed except the tests still pinned to numpy 0.28, which failed on the links conflict, and those
  passed once moved to numpy 0.29. Two changelog items looked relevant: removal of APIs deprecated in 0.27, and
  argument-extraction errors now adding a note to the original `TypeError` instead of replacing it. Neither affects
  the generated bindings or the tests. MSRVs: pyo3 and numpy 1.83, rayon 1.80.

**Follow-ups**
- Anyone pinning numpy 0.28 in their own `@rust` dependencies will hit the `links` conflict after upgrading. Worth a
  release-note line.
- The `abi3-py313` change to the generated `Cargo.toml` is in the Python 3.13–3.15 PR (#28), not here.

---

## 2026-10-06 — Surface rustc errors in `CompilationError` (issue #26, increment 1)

**Why** — A failed build raised only *"Cargo build failed … See build.log for details"*, so finding out what was
wrong meant opening a file deep under `ext/`. This is worst in notebooks, where the log is out of sight. Issue #26
asks for compile errors to be shown inline, and eventually at the right Python line.

**What**
- Cargo now runs with `--message-format=json`. The `compiler-message` records are parsed into `RustDiagnostic`s
  (level, code, message, rendered text, primary-span file and line, whether rustc suggests a fix).
- `CompilationError` gains a `diagnostics` list holding all the errors. Its message is rustc's rendered output for
  the errors that carry a suggested fix (or the first error if none do), a count of the rest, and the path to
  `build.log`.
- If cargo fails before rustc runs (e.g. an invalid `Cargo.toml`), there are no diagnostics. The message then carries
  cargo's stderr from the first `error` line onwards.
- `build.log` still holds readable output: cargo's stderr followed by the rendered errors *and warnings*.
- `RustDiagnostic` is exported, and the README troubleshooting section documents both.

**Design decisions**
- *JSON messages rather than scraping the human output.* The `error[...]` text format isn't stable, but the JSON
  schema is. JSON also gives structured fields (code, primary span), which the next increment needs to map spans
  back to Python lines.
- *Message is rustc's `rendered` text, shortened.* It's the format Rust users already know, and there's no line
  mapping yet that would justify a custom rendering. Warnings are left out of the exception: it should explain the
  failure, and warnings stay in `build.log`.
- *Shortening keeps the sub-diagnostics that point into the crate.* rustc often adds long sections that point into
  std or dependency sources, e.g. a listing of every type that implements `Add`. These are noise for an inline
  error. `_brief` splits the rendered text at sub-diagnostic headers (`help:`, `note:` …) and drops any section with
  a rooted `-->`/`:::` path. Paths inside the crate are relative (`src/lib.rs`), while toolchain and registry paths
  are rooted.
  - *Rooted, not absolute.* The first cut tested `Path.is_absolute()`, which failed on Windows CI. Without the
    `rust-src` component, which the CI runners don't have, rustc reports std as `/rustc/<hash>/library/...`. That
    path has no drive, so it isn't absolute on Windows, and std notes leaked into the message. `Path.anchor`, which
    is a drive and/or root, catches both forms. The `_brief` unit test includes a `/rustc/...` note to pin this.
  - *Rejected: keep only the first section.* That is simpler, but it drops rustc's suggested fixes, such as
    `help: … x.len().try_into().unwrap()`, which are the most useful part of many errors.
  - *Headers are matched by pattern, not indentation.* A first cut started a new section at any line beginning in
    column 0. Line numbers as wide as the gutter (`562 | …`) also start in column 0, so lines of std source leaked
    through. A unit test pins this case.
  - *Multi-line `= help:` items are dropped too.* These are inline lists rather than sections, e.g. E0277's
    "the following other types implement trait `Dimension`:" followed by eight `Dim<…>` types, and they made a
    three-error failure in `examples/loop.py` run to ~45 lines. They are matched as a `= help:` line followed by
    lines indented beyond its `=`. Multi-line `= note:`s (expected/found pairs) and one-line `= help:`s are kept.
  - *Nothing is lost.* `RustDiagnostic.rendered` and `build.log` keep the full text.
- *Only errors with a suggested fix are shown, falling back to the first error.* One mistake often causes several
  errors. In `examples/loop.py`, a `Result` used as a length gave E0271 and E0277 at the `zeros` call, plus E0308 at
  the loop, and only E0308 carried the fix (`n?`). The message dropped from ~45 lines to the ~12 that mattered. A
  "fix" is any child span with a `suggested_replacement` in the JSON; `_select` is a pure function with its own unit
  tests.
  - *Trade-off accepted:* an unrelated error with no fix is hidden while another error has one. The message says
    how many errors are hidden and where to find them, and `diagnostics` still holds them all.
  - *Rejected: first error only.* rustc's emission order isn't a contract, and in `loop.py` it put the knock-on
    errors first.
  - *Rejected: all errors, compacted.* Dropping only the `= help:` lists still left ~35 lines for `loop.py`, most
    of it knock-on noise.
- *Spanless messages are kept, with `file`/`line` left as `None`.* Skipping them would hide linker failures, which
  rustc reports with no source location and, in JSON mode, not on stderr. Spanless notes like "For more information
  about this error…" are filtered out of the exception by level (`failure-note`) but still go to `build.log`.
- *Explicit UTF-8 decoding.* rustc always emits UTF-8, and with `text=True` alone Windows would decode with the
  locale codepage and could raise on non-ASCII source text.
- *`build.log` layout.* It is stderr followed by the diagnostics, rather than the two interleaved as before. The
  order differs slightly from a plain `cargo build`, but nothing is lost. Writing the raw JSON stream was rejected
  as unreadable.

**Follow-ups**
- Increment 2 (on hold): map `src/lib.rs` spans back to the `.py` file and docstring line. This needs `rustfmt` to
  stop reflowing user bodies, e.g. by formatting a skeleton with placeholder bodies and putting the raw docstrings
  back in afterwards.
- Compile errors still only appear on first call. Compiling at decoration time is issue #26's notebook increment 3.

---

## 2026-10-01 — Release prep for 0.1.6

**Why** — Getting ready to release 0.1.6. Refreshing the lockfile pulled in numpy 2.5, which
broke the default `npt.NDArray[...]` mapping at runtime: `test_numpy.py` failed at collection, and
any user annotating with `NDArray` (as the README, SKILL.md and `examples/distance_matrix.py` all
do) got `RustTypeError: Don't know a Rust type for 'NDArray'`. The pre-commit tool bumps also
surfaced new diagnostics.

**What**
- Bumped the version to 0.1.6 and the pre-commit hooks (uv 0.12.21, ruff v0.16.9, ty v0.0.84), and
  refreshed `uv.lock` (numpy 2.4.4 → 2.5.3, among others).
- Added `npt.NDArray` as a `DEFAULT_TYPE_MAPPING` key for `PyReadonlyArrayDyn` alongside the
  existing `np.ndarray` key, and listed both in the type tables in `README.md` and `SKILL.md`.
- Added `# ty: ignore[invalid-argument-type]` to the two `translate_type(npt.NDArray[...])` calls in
  `test_types.py`, and a test for an explicit `np.ndarray[Any, np.dtype[np.float64]]` annotation.
- Applied ruff 0.16's new formatting of Python code blocks in Markdown (two blank lines before
  top-level definitions) to `README.md` and `SKILL.md`.

**Design decisions**
- *Why it broke* — numpy 2.5 redefines `NDArray` as a PEP 695 alias
  (`type NDArray[ScalarT] = ndarray[...]`). `get_origin(NDArray[np.int32])` now returns the
  `TypeAliasType` object `NDArray` rather than `np.ndarray`, so the `np.ndarray` key no longer
  matched.
- *Key the mapping on both `np.ndarray` and `npt.NDArray`.* A first cut replaced `np.ndarray`
  with `npt.NDArray`. That passed on numpy 2.5 but broke every `NDArray` annotation on numpy
  2.4.x (still allowed by `numpy>=2.4.3`, and there `get_origin(NDArray[T])` is `np.ndarray`). It
  also broke explicit `np.ndarray[shape, dtype[T]]` annotations on every version. Keeping both keys
  handles both numpy versions and both annotation styles, at the cost of a duplicate entry (a
  comment in `extension_types.py` explains why both are needed). Raising the floor to `numpy>=2.5`
  was rejected: it drops users for no gain and still needs the `np.ndarray` key for explicit
  annotations.
- *The two keys reach the Rust type by different paths.* `np.ndarray[shape, dtype[T]]` hits the
  `tree.type == np.ndarray` branch in `RustTypeTree.__init__`, which digs `T` out of
  `subtypes[1]`. The numpy 2.5 alias `NDArray[T]` has a single type parameter, so the generic
  branch produces `PyReadonlyArrayDyn<T>` directly.
- *Not expanding type aliases in `PyTypeTree`.* The alternative was to detect
  `typing.TypeAliasType` origins and substitute the arguments into `__value__`
  (`origin.__value__[get_args(t)]`, which yields the old `ndarray[_AnyShape, dtype[T]]` shape).
  That would need no `npt.NDArray` key and would support user-defined `type X = ...` aliases too,
  but it touches the core translation path, so it was left out of this release.
- *ty ignores in the test, not a wider `translate_type` signature* — `translate_type(t: type)`
  already receives non-`type` annotations (`Annotated[...]`, unions), and the tests already use
  this ignore for those. ty 0.0.84 now treats `npt.NDArray[...]` as a type alias, so it joins
  them. Widening the parameter to `Any`/`object` would remove all the ignores but loses precision
  and is out of scope for a release.

**Follow-ups / known limitations**
- Bare `np.ndarray` (no type parameters) still fails with an `IndexError` rather than a helpful
  `RustTypeError`. That predates this change.
- CI only tests the locked numpy (2.5.3). The numpy 2.4 path was checked locally
  (`uv run --with numpy==2.4.4 pytest src/test/test_types.py src/test/test_numpy.py`), but
  nothing in CI would catch a regression there. A lowest-direct-deps CI job would cover it.
- Generic type-alias expansion (see above) remains a candidate for a future change.

---

## 2026-08-30 — Add installable agent skill (`xenoform-rs-skill`)

**Why** — Coding agents (Claude Code and similar) write `@rust`-decorated code more reliably
when given a compact, purpose-built reference instead of relying on the full `README.md` in
context. Bundling one that agents can install directly makes that reference available in any
downstream project using xenoform-rs, not just this repo.

**What** — Added `src/xenoform_rs/skill/SKILL.md`, a bundled agent skill covering the `@rust`
decorator, the type-translation table, common gotchas, config env vars, and when reaching for
`@rust` is actually worth it (performance: unvectorisable loops, cases where compiled code beats
even vectorised numpy, memory pressure, and non-numeric DP/string recurrences — with the
concrete multipliers from the README's own benchmark tables). Added a `src/xenoform_rs/skill_cli.py`
console script, `xenoform-rs-skill`, registered via `[project.scripts]` in `pyproject.toml`, with
`--install [PATH]` / `--remove [PATH]` (default `PATH=.agents`), plus tests in
`src/test/test_skill_cli.py` and a new "Agent skill" section in `README.md`.

**Design decisions**
- *Symlink into the target project rather than copy* — the target
  (`PATH/skills/xenoform-rs`) links to the `skill/` directory shipped inside whatever
  `xenoform-rs` is installed in the active environment, so the skill content always matches the
  installed version with nothing to go stale. Modelled on Streamlit's `streamlit skills` CLI
  (`streamlit/web/skills.py` in the installed Streamlit package), which uses the same
  project-symlink approach for the same reason.
- *Bundled inside the package (`src/xenoform_rs/skill/`) rather than fetched from a URL* — no
  network dependency for install, and confirmed (via `unzip -l` on a built wheel) that
  `uv_build` already packages every non-`.py` file under `src/xenoform_rs/` with no extra
  packaging config, same as the existing `py.typed` marker.
- *No multi-harness detection, no global-install mode, no confirmation prompts* — deliberately
  much simpler than Streamlit's installer: one skill, one target path, symlink-or-refuse. A
  refusal never touches a pre-existing real file/dir or a symlink this script doesn't own.
- *The symlink target is relative where a relative path exists, absolute where none does* — a
  relative target keeps a symlinked skill working if the project directory is moved, but on Windows
  there is no relative path between different drives and `os.path.relpath` raises `ValueError`
  (not `OSError`). CI hit exactly that, with the package on `D:` and pytest's `tmp_path` on `C:`,
  failing every install/remove test on all four Windows jobs; it is also the normal end-user
  layout of a venv on one drive and a project on another. `_link_target` falls back to an absolute
  path there.
- *Console-script entry point rather than a loose script* — `xenoform-rs-skill` resolves
  `Path(__file__).parent / "skill"` from wherever `xenoform_rs` is importable, so it naturally
  targets the venv it's invoked from without any explicit `.venv` path detection.

**Follow-ups** — Only targets `PATH/skills/xenoform-rs` (default `.agents`); could add
multi-harness target dirs (e.g. `.claude/skills`) later the way Streamlit does, if requested.

---

## 2026-07-20 — Add Levenshtein distance example (issue #16 item 3)

**Why** — Issue #16 proposed four examples to showcase rust's performance win beyond
numeric code; item 3 specifically wanted a "String/DP-heavy workload, demonstrating
the win isn't limited to numeric code (and exercises `String`/`&str` argument
handling)". Items 1 and 4 (Mandelbrot, N-body) remain open; item 2 (Monte Carlo) was
done in #18.

**What** — Added `examples/levenshtein.py`: `levenshtein_distances_py` computes the
Wagner-Fischer edit distance (rolling-row DP) from a query word to every word in a
synthetic, seeded wordlist; `levenshtein_distances_rust` is the `@rust`-decorated,
single-threaded equivalent. Wired into CI's "Run examples" step and the
`AGENTS.md` Quality Gates / Repository Layout lists, with a matching new "Levenshtein
distance" README section (prose, code, timing table).

**Design decisions**
- *No numpy baseline, unlike the other three examples* — the DP recurrence is over
  strings one character at a time; there's no natural vectorised form the way there is
  for the numeric examples, so this is deliberately a plain-python-vs-rust comparison
  (like `loop.py`), which is itself the point: the win isn't limited to workloads numpy
  can also accelerate.
- *`query: Annotated[str, "&str"]`, `wordlist: list[str]`* — chosen to exercise both
  ends of the type-mapping table in one signature: `list[str]`/`list[int]` fall out of
  the *default* mapping (`Vec<String>`/`Vec<i32>`, no annotation needed), while `query`
  uses the `Annotated` override to borrow (`&str`) rather than clone the one string
  compared against every word in the list - the override mechanism actually earning
  its keep here, not just demonstrated for its own sake.
- *Single-threaded rust, no rayon* (maintainer's call, offered as an explicit either/or)
  — each word's distance is independent so `into_par_iter()` would be a one-line
  addition, but `distance_matrix.py` and `monte_carlo.py` already cover the rayon
  story, and issue #16 framed this example's point as DP/string handling, not
  parallelism. Mirrors how `distance_matrix.py` itself shipped single-threaded first
  and was parallelised later in a separate PR (#21) - left as a natural, low-risk
  follow-up rather than conflating two lessons in one diff.
- *Rust allocates a fresh DP row per character, matching the python baseline's own
  allocation pattern* rather than hand-optimising with a reused scratch buffer - keeps
  the comparison honest (same algorithm, compiled vs interpreted) rather than
  bundling an algorithmic/allocation improvement into the speedup number, the same
  reasoning as the Monte Carlo and distance-matrix examples' baseline choices.
- *Synthetic seeded wordlist (`random.Random(19937)`, lowercase, length 3-12) rather
  than a real dictionary file* — every existing example generates its own data rather
  than depending on an external file or OS-provided wordlist (e.g. `/usr/share/dict/words`,
  which isn't reliably present on Windows CI runners); this keeps the example
  self-contained and reproducible across the whole CI matrix.
- *Wordlist sizes capped at 1,000,000* (1,000/10,000/100,000/1,000,000, mirroring
  `loop.py`'s range one step short) — calibrated empirically: the pure-python baseline
  costs a fixed ~6.7us/word regardless of list size, so 1M words costs ~7.5s, the same
  order of magnitude as `loop.py`'s slowest case (1.9s at 10M rows). Going a further
  order of magnitude (10M) would push the python baseline past a minute across the CI
  matrix for no additional insight, since the ~28x speedup is already flat across
  sizes.
- *Exact-equality assertion between implementations* rather than a statistical bound
  (unlike Monte Carlo) — edit distance is a deterministic integer computation with no
  RNG in the algorithm itself (only in generating the wordlist), so the two
  implementations must agree exactly, not just within error bounds.

**Follow-ups** — Parallelising `levenshtein_distances_rust` across the wordlist with
`rayon` is a natural, low-risk follow-up (each word is independent). Items 1 and 4 of
#16 (Mandelbrot, N-body) remain.

## 2026-07-20 — Document Monte Carlo memory profiling

**Why** — The Monte Carlo example's README section already compared wall-clock time
for `numpy+threads` vs `rust+rayon`, but the design decisions behind it (#18) had
already identified memory as the more dramatic difference — numpy must materialise
the whole `(n_paths, n_steps)` matrix while rust holds each path in a register — yet
that was never actually measured, only asserted.

**What** — Ran a one-off local peak-RSS measurement of both implementations at the
same three path counts as the timing table (100k/300k/1M) and added the results as a
new subsection in the README, alongside the existing timing table. No code changed in
`examples/monte_carlo.py`; this is a documentation-only update.

**Design decisions**
- *Peak RSS via `resource.getrusage(RUSAGE_SELF).ru_maxrss`, not `tracemalloc`* —
  `tracemalloc` only sees Python-domain heap allocations. It's blind to rust's own
  allocator entirely (the very thing being measured), and doesn't cleanly see numpy's
  array buffers either without relying on numpy's undocumented tracemalloc-domain
  registration. OS-level RSS is allocator-agnostic and answers the question that
  actually matters (the 7GB CI-runner OOM risk noted in #18).
- *Each (implementation, n_paths) measured in its own fresh subprocess* — `ru_maxrss`
  is a process-lifetime high-water mark that never decreases. Measuring both
  implementations sequentially in one process (as the timing loop does) would leak
  whichever ran first — typically numpy's ~2GB — into every subsequent reading,
  including rust's. Isolating each call in a fresh subprocess makes each number
  reflect only that one call.
- *One-off measurement, not wired into the script or CI* (per maintainer's steer) —
  a permanent version would need either an OS-conditional fallback (`resource` is
  POSIX-only, and CI runs Windows) or a new dependency (e.g. `psutil`) to poll a
  child process cross-platform, plus 6 extra subprocess spawns on every CI run for
  little ongoing benefit. Simpler to record the numbers once and revisit if the
  library or example changes enough to invalidate them.
- *Numbers are linux/python 3.13, same box as the existing timing table (22 cores)* —
  not re-measured per-OS; `ru_maxrss` units differ between linux (KiB) and macOS
  (bytes), called out in the README so anyone reproducing this on macOS doesn't get
  caught out.

**Follow-ups** — If a future example needs memory regression protection in CI (rather
than a one-off illustrative number), revisit the subprocess-isolation approach above
and decide then whether `psutil` earns its keep as a new `examples`-extra dependency
for Windows coverage.

## 2026-07-20 — Move `verbose` to config, stop clobbering root logging (#13)

**Why** — Two related #13 items. `verbose` was a per-call `rust(...)` decorator arg,
which meant every decorated function had to repeat it and it couldn't be toggled
globally (e.g. for CI or debugging someone else's code) without editing source.
Separately, `verbose=True` called `logging.basicConfig(force=True)`, which
reconfigures the *root* logger — `force=True` strips out any handlers the host
application had already installed, silently breaking their logging setup.

**What** — `verbose` moved from a `rust()` kwarg to `XenoformConfig.verbose: bool`
(env var `XENOFORM_RS_VERBOSE`), picked up on each `rust()` decoration via
`get_config().verbose`. Replaced the `basicConfig` call with a new
`_configure_verbose_logging()` that only touches the library's own
`logging.getLogger(__name__)`: sets its level to INFO, attaches a `StreamHandler`
with the same timestamped format, and sets `propagate = False` so the messages
never reach the root logger (or a host's handlers on it) at all — fully isolated in
both directions. Guarded with `if not logger.handlers` so repeated `rust()` calls
(one per decorated function) don't stack duplicate handlers. Updated the two tests
that passed `verbose=True` to the decorator (now a `TypeError`, the arg is gone),
added `test_verbose_logging.py` covering isolation-from-root and idempotency, and
updated the README's decorator-parameter table and troubleshooting section.

**Design decisions**
- *`propagate = False` rather than leaving the default `True`.* The point of #13 was
  isolation; leaving propagation on would print duplicate lines whenever a host
  app's root logger also had a handler, and would still let host root-logger *filters*
  suppress our messages depending on host config — neither of which "isolated" was
  meant to allow.
- *`str | None`, matching `disable_ft`'s existing pattern, over `bool`* (reverted after
  first trying `bool`). pydantic-settings' bool parsing rejects an empty string, so
  `XENOFORM_RS_VERBOSE=` (set but empty - the natural way to flip on a flag from a
  shell one-liner, `XENOFORM_RS_VERBOSE= uv run ...`) would fail validation instead of
  enabling verbose logging. `str | None` sidesteps that: any set value, including
  empty, is truthy for our purposes, checked the same way as `disable_ft` via
  `is not None`.
- *Read via `get_config().verbose` at each `rust()` call rather than snapshotted at
  import*, unlike `extmodule_root` (a pre-existing, separately-tracked #13 item). Since
  `rust()` runs once per decorated function rather than once per process, there's no
  extra cost to reading it live, and it means `XENOFORM_RS_VERBOSE` set later in a
  process (e.g. by a test fixture) is honoured by decorations that haven't run yet.

**Follow-ups** — None for this item. The rest of #13 (shared cargo target dir, sidecar
checksum file, error surfacing, configurable timeout, lazy rustc check, build
locking, `int → i64`, and the `extmodule_root` snapshot-at-import item) is untouched.

## 2026-07-19 — Parallelise the distance-matrix example with rayon (#21)

**Why** — The distance-matrix example computed its rust kernel single-threaded, so it
demonstrated only the compiled-loop win, not multi-core scaling. `rayon` was already in
the toolbox from the Monte Carlo example (#18); applying it here is a natural,
self-contained showcase of parallelism on a numpy-backed operation.

**What** — Replaced the sequential upper-triangle kernel in
`examples/distance_matrix.py` with a rayon-parallel fill: `par_chunks_mut(n)` hands each
task one disjoint row of a flat `Vec<f64>`, which is then reshaped into the `PyArray2`
result. Added a warm-up call before the timing loop, updated the README section (prose,
code, and timing table), and bumped the version to 0.1.5. The loop example was also
switched from `process_time` to `perf_counter` with its own warm-up.

**Design decisions**
- *Dropped the symmetry optimisation rather than parallelising it.* The original kernel
  filled only the upper triangle and mirrored each value into `[j, i]`. That mirror-write
  is exactly what blocks a naive parallelisation over `i`: the task for row `i` writes into
  row `j` while the task for row `j` also writes row `j` — a data race. Filling one full
  row per task makes each task's output disjoint, so the borrow checker proves the writes
  race-free with no `unsafe`. The cost is computing every pair twice (~2× arithmetic), but
  the embarrassingly parallel scaling more than pays for it: the 10000-point speedup goes
  from ~9× to ~50–57× over single-threaded numpy.
- *Fill a plain `Vec` then reshape, rather than writing into `PyArray2::zeros` via
  `as_array_mut`.* Sharing a mutable numpy view across rayon threads would need `unsafe`
  and manual non-aliasing reasoning; a `Vec` + `par_chunks_mut` keeps the whole thing safe,
  and `PyArray1::from_vec(...).reshape([n, n])` is a cheap final materialisation.
- *Warm-up call before timing.* rayon's one-off global threadpool spin-up (~370 ms on the
  first parallel call) otherwise lands on the first timed size and misrepresents per-call
  cost — the same reasoning as the Monte Carlo example (#18).
- *Honest baseline framing in the README.* The ~50× headline is against *single-threaded*
  numpy, so it bundles rust's per-element win with the core count — unlike the Monte Carlo
  example, whose numpy baseline is already thread-sharded. The prose notes the full-matrix
  trade-off so the comparison isn't oversold.

**Follow-ups** — The numpy baseline here is single-threaded; a thread-sharded numpy
distance matrix would isolate rust's per-core advantage (as the Monte Carlo example does),
if a fairer head-to-head is ever wanted.

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
