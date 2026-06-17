---
name: issue-create
description: Use when the user has an implementation plan and wants to file feature-unit GitHub Issues in English. Single issue → no Epic, no confirmation; multiple issues → add an Epic parent linking children via checklist
argument-hint: "<plan-file-path>"
allowed-tools: Bash(gh:*), Read, AskUserQuestion
---

# Create Feature-Unit Issues from a Plan

Convert a plan document (typically under `.claude/superpowers/plans/` or `docs/`) into a set of English GitHub Issues at **feature-unit** granularity, plus one Epic parent.

## Usage

```bash
/issue-create .claude/superpowers/plans/2026-05-29-web-ui-phase1-plan-a.md
```

## Workflow

1. **Read the plan file** passed as `$ARGUMENTS`. Identify discrete tasks.

2. **Group tasks into feature units.** A feature unit is something that can be PR'd independently. Decide single vs. multiple by the work, not a fixed target:
   - **Single issue** (1 PR / spike / small feature) → file exactly one issue, **no Epic**. Avoid over-splitting.
   - **Multiple issues** (4–8 typical) → file the children **and** an Epic parent. Avoid 1-issue-per-task (too noisy) and 1-or-2 mega-issues (too coarse).

3. **Inspect existing labels and milestones** so the new issues fit the project's conventions:

   ```bash
   gh label list --limit 30
   gh issue list --state open --limit 5
   gh api repos/<owner>/<repo>/milestones
   ```

4. **Granularity & Epic — decide without asking.**
   - **Single issue:** create it directly. No confirmation, no Epic.
   - **Multiple issues:** include an Epic parent by default. Only use `AskUserQuestion` if the grouping is genuinely ambiguous; otherwise proceed with your proposed grouping.
   - Always reference spec/plan paths in issue bodies (even if `.claude/` is gitignored).

5. **Draft each issue** with the following structure (English only):

   ```markdown
   ## Goal
   <1–2 sentence outcome>

   ## Scope
   - <files / modules touched>
   - <key design decisions>

   ## References
   - Spec: `<path>` (note "gitignored, local only" if applicable)
   - Plan: `<path>` Tasks <N>–<M>

   ## Acceptance Criteria
   - [ ] <observable behavior>
   - [ ] <test passes>
   ```

   Title: use Conventional Commits prefix (`feat:` / `feat(scope):` / `chore:` / `fix:` / `docs:`) and keep under 70 characters.

6. **Create child issues** with `gh issue create`. Default label: `enhancement`. Use HEREDOC for body:

   ```bash
   gh issue create --label enhancement \
     --title "feat(web): add /api/config GET/PUT with Pydantic v2 schemas" \
     --body "$(cat <<'EOF'
   ## Goal
   ...
   EOF
   )"
   ```

7. **Create the Epic (multiple-issue case only — skip for a single issue)** referencing children by issue number with checkbox markdown. Capture child URLs into shell variables and `basename` them to get numbers:

   ```bash
   URL1=$(gh issue create ...)
   N1=$(basename "$URL1")
   ...
   gh issue create --label enhancement \
     --title "epic: Phase 1 Plan A — Web API backend foundation" \
     --body "$(cat <<EOF
   ## Sub-issues
   - [ ] #$N1 — <short label>
   - [ ] #$N2 — <short label>
   ...
   EOF
   )"
   ```

   Note: Epic body uses unquoted HEREDOC so `$N1` etc. expand. Child bodies use quoted HEREDOC (`'EOF'`) to keep markdown verbatim.

8. **Report** the URLs back to the user as a markdown table.

## Conventions

- **Language:** Issue titles, bodies, and the Epic are all English. Skill conversation with the user may be in Japanese.
- **Labels:** Default to `enhancement`. If the project has a more specific label (e.g., `feat`, `backend`), prefer that.
- **Title prefix:** `feat:` for new features, `chore:` for plumbing/refactors that ship no behavior, `fix:` for bugs, `docs:` for documentation. Use scopes (`feat(web):`, `feat(scope):`) when one PR touches a clear subsystem.
- **Acceptance Criteria** are observable from outside the code: HTTP status codes, command exit codes, file presence, specific test names passing. Avoid "code is clean" / "well-structured".
- **One PR per child issue** is the default. Mention this expectation in the Epic if the user confirms it.

## Anti-patterns

- Filing one issue per `Step` in the plan (too granular)
- Filing one giant "implement Plan X" issue (defeats the point)
- Mixing languages within a single issue
- Burying spec/plan references at the bottom — put them in their own `## References` section so reviewers can navigate
- Re-pasting the entire plan into the issue body — link to it instead and extract the relevant Tasks/Steps numbers
