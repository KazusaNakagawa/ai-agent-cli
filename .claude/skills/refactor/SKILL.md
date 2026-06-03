---
name: refactor
description: Use when the user asks to refactor or split up large files / components ("リファクタできる?" "コンポーネント化", "分割しよう"). Surveys the codebase by LOC, classifies concerns within hotspots, and proposes an ordered multi-PR sequence (low-risk first), then executes step-by-step with a PR per step.
argument-hint: "[path-or-glob]"
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion, TaskCreate, TaskUpdate
---

# Refactor: Survey → Plan → Sequence → Execute

A repeatable refactoring workflow. Produces a **multi-PR plan** with risk-ordered steps, then drives each step independently so reviewers can land them one at a time.

## Usage

```bash
/refactor              # Survey the whole repo
/refactor apps/web     # Limit the survey to one subtree
```

## Workflow

### Phase 1 — Survey (LOC hotspots)

Run from the repo root. Adapt the find pattern to the project.

```bash
# Frontend / TS
find apps/web -type f \( -name "*.tsx" -o -name "*.ts" \) \
  -not -path "*/node_modules/*" -not -path "*/.next/*" \
  | xargs wc -l 2>/dev/null | sort -rn | head -20

# Python
find apps/python/src -type f -name "*.py" \
  | xargs wc -l 2>/dev/null | sort -rn | head -20
```

Pick candidates above ~300 LOC. Read each top-3 file in full before classifying.

### Phase 2 — Classify concerns

For each hotspot, identify **discrete concerns** that can be extracted. Examples:

| Pattern | Extraction kind |
|---|---|
| `useState` + persistence I/O effect | custom hook |
| Browser API wrapper (Speech, IndexedDB, …) | custom hook |
| Per-resource fetch + state | custom hook |
| JSX block with its own loop / render logic | component |
| Pure data transform (markdown → blocks, parsing) | module-level helper file |
| Network client wrappers + pure formatters in one file | split into 2 files |

Output a table per hotspot before any code change:

```markdown
| Name | Concern | LOC |
|---|---|---|
| useDraftPersistence | sessionStorage-backed draft | ~30 |
| ChatMessageList | message rendering | ~70 |
```

### Phase 3 — Sequence the PRs

Order the steps by **risk × independence**, not by impact. The rules:

1. **Pure hooks / helpers first** (no JSX, no shared state) — lowest risk.
2. **Component extractions next** — pure JSX moves with prop wiring.
3. **Stateful / orchestration extractions last** — where the cross-file ref/state plumbing actually moves.
4. **Cross-language splits in any order** — Python file split vs frontend refactor are independent; let the user pick when convenient.

Present the sequence with diff estimates and main risk for each step. Reasonable size: **150–250 LOC per PR**. If a single step exceeds 400 LOC moved, break it further.

### Phase 4 — Confirm with the user

Ask via `AskUserQuestion`:

- Which step to start with (offer "report only" as an option — the user may want just a plan)
- Whether to do all steps in this session or pause between

Default to **one step at a time, with a PR per step**. Do not chain.

### Phase 5 — Execute one step

For each step:

1. `git checkout <main-branch>` and pull. Use the project's working branch (`dev` here, `main` elsewhere — check `git config init.defaultBranch` or recent commits).
2. `git checkout -b refactor/<scope>-<short-action>` (e.g. `refactor/chatform-hooks-extract`).
3. Create / move code. **No behavior changes.** If a behavior bug surfaces, file it separately — do not bundle.
4. Run the project's verification commands in parallel:
   - Tests (`npm run test`, `pytest -v`, etc.)
   - Lint (`npm run lint`, `ruff check`, etc.)
   - Type check (`npx tsc --noEmit`, `mypy`, etc.)
5. **Tests must remain green at the same count.** If a number changes unexpectedly, stop and investigate.
6. Commit with a Conventional Commits message scoped `refactor(<area>):` plus a `Co-Authored-By` line.
7. Push and open the PR. The PR body must include:
   - A "Step N of M" header so reviewers know the sequence.
   - The list of remaining steps (for context).
   - A test plan checklist that explicitly says "no behavior changes".

PR title template:

```text
refactor(<scope>): <what was extracted into where>
```

PR body skeleton:

```markdown
## Summary
Step **N of M** of the <area> refactor sequence. <one-line outcome>.

| Hook / Component | Concern | LOC |
|---|---|---|
| ... | ... | ... |

No behavior changes. <Any deferred concerns and why.>

## Test plan
- [x] <test command> — N tests pass (unchanged from baseline)
- [x] <lint command> — clean
- [x] <typecheck command> — clean
- [ ] Manual smoke: <happy path features that touch the changed code>

## Refactor sequence (for context)
1. <step 1> ✅
2. **This PR**
3. <step 3>
4. <step 4>
```

### Phase 6 — Stop and wait for merge

After the PR is open, **stop**. Do not auto-merge. Do not start the next step until the user confirms.

When the user says to continue:

1. `git checkout <main-branch>` and `git pull` to pick up the merged refactor.
2. Move to the next step in the sequence.

## Conventions

- **No behavior change in refactor PRs.** If you find a bug while extracting, file an Issue, do not fix it inline.
- **Tests stay green at the same count.** Adding tests during refactor is allowed only if they cover the new extracted unit's public API; do not change existing test assertions.
- **One PR per step.** Resist the urge to combine "while I'm in there" extractions.
- **Naming.** Hooks use `use<Concern>` camelCase; components match the existing project convention (PascalCase under `components/`); Python module splits use snake_case.
- **Comments survive the move.** When you move a block, move its comments too. Update them only if they referenced a now-incorrect location.
- **Diff hygiene.** Reorder imports alphabetically when adding new ones so the diff is clean.

## Anti-patterns

- **The mega-PR.** One PR moving 1000+ LOC. Reviewers can't load it.
- **Refactor + feature in the same PR.** "While I was extracting the hook I also added X." Always split.
- **Refactor + bug fix in the same PR.** Same reason.
- **Test churn without need.** Refactor PRs that diff hundreds of test lines almost always changed behavior accidentally.
- **Skipping verification between steps.** Each step's PR must include the verification output, not "I'll run them at the end."
- **Renaming during extraction.** Move first, rename in a separate PR — the diff stays reviewable.
- **Premature abstraction.** Don't extract a hook that has exactly one caller and isn't reused elsewhere unless it's a genuine concern boundary.

## Survey heuristics

When picking what to extract from a hotspot:

- **A `useEffect` + matching cleanup is almost always a hook.**
- **Anything that talks to `window.*` or `navigator.*` is almost always a hook.**
- **A `useState` whose value never leaves the file is almost always extractable.**
- **A JSX block over 40 lines that maps over a list is almost always a component.**
- **A `<form>` / `<textarea>` cluster with its own handlers is almost always a `<Composer>` style component.**
- **Two unrelated public functions in the same file (e.g., a converter and an API client) are almost always two files.**

## Skipping the workflow

If the user explicitly says "just the survey", "report only", or "plan のみ", stop after Phase 3 and return the table. Do not branch, do not edit. The skill is also useful as a planning aid without execution.
