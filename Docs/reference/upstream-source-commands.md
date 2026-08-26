# Locked upstream source commands

Open this reference only when the locked pydcs or BriefingRoom cache is not
ready, or when its provenance needs review. Normal discovery commands consume
the cache but never acquire or repair it. Current CLI help remains
authoritative for syntax.

## Product cache layout

Use an explicit disposable cache root. The documented layout is:

```text
output\upstream\
  pydcs\
  briefing-room-for-dcs\
```

These are third-party Git checkouts, not DCSMizzer source or generated mission
content. Do not commit or redistribute them with DCSMizzer. Keep the license
file supplied by each upstream project in its checkout.

The product lock is:

| Cache directory | Remote | Branch | Commit | Git tree | License |
|---|---|---|---|---|---|
| `pydcs` | `https://github.com/pydcs/dcs` | `master` | `e20f328390aecaac2a7f82444b4f5a96ac6bb2c3` | `b07fadf3dddd0873176eab32c15caa4c34c46b0f` | LGPL-3.0-only, upstream `LICENSE.txt`, SHA-256 `ea7d049c7705dc13afc202dd18e1827f3484f8212fd3fa7b82fc4a0c363432c9` |
| `briefing-room-for-dcs` | `https://github.com/DCS-BR-Tools/briefing-room-for-dcs` | `main` | `4d8773e9eec0215edb5cd9f576c085ee9f1bf7a7` | `75898835689457be82ffa08693aaadae92e28117` | GPL-3.0-only, upstream `LICENSE`, SHA-256 `a0ee746064b06d09cab0768116ec265fd0d45261d4087c9ad2c698a07c7aac0e` |

A branch name identifies provenance but does not authorize moving to its
current tip. Evidence is accepted only at the fixed commit and tree.

## `upstream-status`

Check readiness before any upstream-backed query:

```powershell
python Tools\dcsmizzer.py upstream-status --cache-root output\upstream
```

`upstream-status` is strictly read-only. It checks both expected child
directories, their exact Git top-levels, sanitized remotes, locked commits and
trees, worktree cleanliness, required paths, and exact license-file hashes. It
does not fetch, checkout, repair, create, or delete anything.

Exit code 0 means both locked sources are ready for the downstream
provenance-gated readers. Exit code 1 means the cache was inspected but at
least one source is absent, dirty, mismatched, or otherwise not ready. Exit
code 2 means the command could not safely inspect the requested path or the
invocation was invalid. A nonzero result is not permission to use a different
commit or silently downgrade the evidence.

## `upstream-prepare`

Prepare both locked checkouts when status is not ready:

```powershell
python Tools\dcsmizzer.py upstream-prepare --cache-root output\upstream
python Tools\dcsmizzer.py upstream-status --cache-root output\upstream
```

`upstream-prepare` is the only product command allowed to contact the network
or write the upstream cache. It contacts only the fixed HTTPS repositories,
selects the locked commits above, then verifies the resulting commit, tree,
clean worktree, and license presence. A Git fetch may retain branch-history
objects, but the usable worktree never advances to a newer branch tip.

The command may fetch and detach a clean recognized checkout at the fixed
commit. It refuses to clean or reset a dirty checkout, adopt the wrong remote
or a non-exact Git root, or overwrite an unrelated child. Exit code 0 means
both checkouts reached the locked ready state. Exit code 1 means preparation
completed far enough to report an unready source but did not establish the
full locked state. Exit code 2 means a usage, unsafe-path, or unhandled
filesystem/API error prevented the command from safely operating on the cache.
Git clone, fetch, checkout, or pinned-object failures that can be reported
safely remain structured preparation results and return exit code 1. Run
`upstream-status` again before consuming the cache; do not infer readiness
from directory presence.

For a network-isolated run:

```powershell
python Tools\dcsmizzer.py upstream-prepare `
  --cache-root output\upstream `
  --offline
```

`--offline` forbids network access. Preparation may use only Git objects
already present inside the supplied cache. Missing locked objects therefore
fail nonzero; the command never substitutes another revision.

## `upstream-promotion-audit`

Review one clean candidate without advancing the immutable product lock:

```powershell
python Tools\dcsmizzer.py upstream-promotion-audit `
  --cache-root output\upstream `
  --candidate-root output\upstream-candidates\briefing-room-for-dcs `
  --source BriefingRoom
```

Both roots are explicit and read only. The command first requires the complete
baseline cache to pass its existing lock gate. It then requires the candidate
to be the exact Git top level, clean, on the expected branch or detached, on
the recognized credential-free remote, locally configured without dangerous
Git hooks/helpers, complete at every required path, and unchanged in license.
The checkout must use a standalone, non-shallow object store without replace
refs, grafts, alternates, or sparse-checkout state. Every tracked consumer file
must be a safe regular file with normal index flags and bytes matching its Git
blob; built-in CRLF checkout normalization is accepted only for the known text
formats. Ignored files that the bounded parser could consume fail the audit.
The locked commit must exist in the candidate object database and be an
ancestor of its exact `HEAD`.

The audit records a resource-bounded, complete `--name-status --no-renames`
path diff, its canonical hash, and the subset of paths DCSMizzer actually
consumes. Git capture, consumer-file count, individual size, and aggregate
size limits fail closed instead of silently truncating the decision. A
consumed pydcs change triggers full static fingerprints over all five unit
categories, every plane/helicopter task and pylon edge, the weapon and task
registries, and all parsed terrain/airport/parking summaries. A consumed
BriefingRoom change fingerprints all theatre declarations, airbases, parking,
bounds, and project-version evidence; changed spawn-point files are additionally
streamed and parsed in full. Parser incompleteness or a worsened unresolved
record count fails closed. Both parsed models must be identical across two
passes, and the baseline/candidate repository identities are checked again
after parsing, so ordinary mid-audit changes cannot pass.

The machine decision is intentionally narrower than “upgrade”:

- `no_revision_change`: candidate and lock are identical;
- `retain_pin_consumed_model_unchanged`: the branch moved, but the bounded data
  model used by DCSMizzer did not;
- `candidate_requires_repository_regression`: consumed data changed and the
  candidate passed the read-only compatibility gate;
- `reject_candidate`: identity, ancestry, diff, stability, or parser validation
  failed.

Exit code 0 means the audit is complete and reviewable. It authorizes at most
the next repository-regression step. `automatic_pin_update` and
`lock_update_authorized` are always false. Before an explicit lock edit, retain
the exact audit report, review its relative paths and component hashes, and run
the complete product, survey, documentation, Prompt, style, and compilation
suites. After an approved edit, rebuild the disposable cache, require
`upstream-status` to pass, create a clean evidence snapshot, and inspect its
diff/readiness result. Exit code 1 means the candidate failed this audit; exit
code 2 means the invocation or safe inspection could not be completed.

No audit Git query fetches, lazily downloads, checks out, imports, or executes
upstream content. Candidate acquisition and fast-forward maintenance remain an
explicit development evidence task outside this product command. A dirty
checkout is never reset or cleaned automatically.

## Execution and trust boundary

None of these commands imports or executes upstream Python, runs BriefingRoom,
starts DCS, or starts Mission Editor. Downstream `pydcs-*`, `br-*`, and
`terrain-coverage` commands continue to parse a bounded set of data and source
declarations without executing upstream code.

Command implementation and source readiness are separate facts. The commands
can be implemented while a particular machine's cache is absent or unready.
Only a zero `upstream-status` result establishes that the external
prerequisite is ready. When an acknowledged locked source participates in a
required `audit-spec` determination, an unready or mismatched source is a hard
audit failure, not a warning.
