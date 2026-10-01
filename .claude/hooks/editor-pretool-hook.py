#!/usr/bin/env python3
"""
PreToolUse hook for editor mode — blocks tool execution outside allowed slugs.

Reads `.codeyam/editor-step.json` for the active slug and
`.codeyam/cache/step-metadata.json` for the per-slug capability
allowlists, then blocks:
- Write/Edit to non-`.codeyam/`, non-`.claude/` files at slugs that
  don't carry the code-change capability.
- Bash `git commit` / `git add` outside slugs in `commitSlugs`.
- Bash `git push` outside slugs in `pushSlugs`.
- Bash test runs (`refresh-tests` / raw runners) at slugs NOT in
  `testRunSlugs` — every phase whose `test_scope` is `none`. Pre-Demo
  slugs are blocked to hold the prototype-speed "no tests before Demo"
  boundary; post-hardening slugs (presentation, journal, sync, commit,
  push) are blocked because a test run is out of scope at a gate. The
  `noTestSlugs` projection says which kind a slug is, so the refusal
  names a recovery that actually exists at that position.
- AskUserQuestion at slugs in `previewRequiredSlugs` unless
  `.codeyam/preview-shown.json` matches the current step.

One rule is deliberately NOT step-scoped: the scripted-source-rewrite
guard. CLAUDE.md's ban on machine-rewriting tracked source holds in
every session, editor mode or not, so that guard runs before the
`CODEYAM_EDITOR_ACTIVE` short-circuit in `main`.

The slug allowlists are projected into the cache by
`crates/codeyam-editor/src/commands/editor/slug_capabilities.rs` (the
single source of truth for per-slug capabilities), so a future
workflow renumbering never silently breaks a gate.

The Plan-tab PTY does not set `CODEYAM_EDITOR_ACTIVE`, so this hook is
silent there by design — Plan-tab commits are always allowed.

Returns exit code 2 to block, 0 to allow. Stderr is fed back to
Claude as feedback, and every refusal carries an `Evidence:` line
stating what was actually observed — the resolved project dir, the
file consulted, expected versus found — so a block is debuggable
without reading this source.

Heredoc bodies are elided before any command is lexed
(`elide_heredoc_bodies`): a commit-message body is data by shell
semantics, and lexing one as shell turned backticked code spans into
commands and a single apostrophe into an unterminated quote that
failed four guards closed at once.

Run with `--explain` to get the verdict and its evidence on STDOUT at
exit 0, changing nothing: it records no repeat fingerprint and never
writes to stderr. The flag is read from argv only — never from the
environment or the event — so nothing on the enforcement path can
reach it.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time

# `_step_metadata` lives next to this file; add the hook directory to
# `sys.path` so the import works regardless of the cwd the hook runner
# launches from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _step_metadata import cli_command, load_step_metadata, resolve_mode_table  # noqa: E402

# Plan files live here and are always commitable regardless of current step.
PLAN_PATH_PREFIX = ".codeyam/plans/"


def staged_paths_are_plans_only(project_dir):
    """True iff `git diff --cached --name-only` is non-empty and every path
    starts with `.codeyam/plans/`. An empty staged set returns False — the
    commit would be a no-op and the existing error path is more useful."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    if not lines:
        return False
    return all(l.startswith(PLAN_PATH_PREFIX) for l in lines)


def git_add_paths_are_plans_only(command):
    """True iff a `git add` command targets only paths under .codeyam/plans/.

    Conservatively rejects any flag-like arg (-A/--all, -p/--patch,
    -i/--interactive, etc.) and a bare "." pathspec, since we cannot infer
    the eventual staged set in those cases."""
    tokens = command.split()
    try:
        add_idx = tokens.index("add")
    except ValueError:
        return False
    args = tokens[add_idx + 1:]
    if not args:
        return False
    for tok in args:
        if tok.startswith("-") or tok == ".":
            return False
    return all(p.startswith(PLAN_PATH_PREFIX) for p in args)


def merge_in_progress(project_dir):
    """True while a rebase, merge, or cherry-pick is paused mid-operation.

    Staging a conflict resolution is not the same act as creating a commit, but
    both spell `git add`. `pre-commit-sync` starts a rebase and, on a
    modify/delete conflict in the regenerated test-cache blobs, prints a
    recovery that ends in `git add -- <path>` — which the commit-slug gate then
    refused, wedging the very step that printed it. The gate was always this
    broad; it only became reachable once the hook's exit code stopped being
    swallowed. `git commit` stays gated regardless, so this cannot land a commit
    outside the commit slug — it only lets an in-flight rebase be finished."""
    git_dir = os.path.join(project_dir, ".git")
    return any(
        os.path.exists(os.path.join(git_dir, marker))
        for marker in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD")
    )


def _slug_label(state, slug):
    """Human-readable identifier for BLOCKED messages. Slug is the
    primary handle; label is shown alongside when state carries it."""
    label = state.get("label", "") or ""
    if label:
        return f"{label} (slug={slug})"
    return f"slug={slug}"


def _commit_gate_phrase(commit_slugs):
    """Name the slug(s) a refusal should steer the agent toward, rendered
    for prose ("`commit`", "`assist-wrap`", "`a` / `b`").

    Derived from the active mode's own `commitSlugs` rather than written
    out, because the literal `commit` is the BUILD flow's gate. An assist
    session's one approval gate is `assist-wrap`, so a hard-coded
    "advance until the `commit` slug" told that session to walk toward a
    slug its 4-step track does not contain. For the build flow the set is
    `["commit"]` and this renders exactly the previous wording."""
    slugs = sorted(s for s in (commit_slugs or []) if isinstance(s, str))
    if not slugs:
        return "`commit`"
    return " / ".join(f"`{s}`" for s in slugs)


_REFUSAL_LOG = os.path.join(".codeyam", "state", "refusal-fingerprints.json")

# How long a refusal stays "recent" for repeat detection. Long enough to
# span the retry loops seen in the transcripts (four blocks inside 65
# seconds, two of them one second apart), short enough that a genuine
# return to the same slug an hour later is not scolded as a repeat.
_REPEAT_WINDOW_SEC = 600

# Cap on retained fingerprints. This is a debounce hint, not durable
# state — an unbounded file would grow for the life of the branch.
_REFUSAL_LOG_MAX = 40

# How many times a RULE must have been refused — ever, across sessions and
# across differing arguments — before its block announces itself as a
# recurring trap. Three, because the measured shape is one refusal per
# session (the journal-timestamp guard fired in five separate sessions,
# exactly once in each), so by the third the agent is rediscovering
# something the project already documents.
_RULE_RECURRENCE_MIN = 3

# Cap on the per-rule aggregate. Unlike `entries` this half IS durable — it
# has to outlive the session to see a cross-session repeat at all — so what
# bounds it is the hook's closed set of rule names, not a time window.
_RULE_LOG_MAX = 64


def _ordinal(n):
    """`3` -> "3rd". Pure, so the 11/12/13 exceptions are assertable
    without emitting a refusal."""
    if n % 100 in (11, 12, 13):
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _capped_rules(rules):
    """The per-rule aggregate trimmed to the most recently seen rules.

    The map is keyed on the hook's own closed set of rule names, so it is
    already small in practice. The cap makes boundedness a property of the
    file rather than of the caller — a rule name that ever becomes dynamic
    must not be able to grow this file for the life of the branch.
    """
    if len(rules) <= _RULE_LOG_MAX:
        return rules
    ordered = sorted(rules.items(), key=lambda kv: kv[1].get("lastAt", 0))
    return dict(ordered[-_RULE_LOG_MAX:])


def _load_refusal_log(path, now):
    """Read the refusal log at `path` as `(entries, rules)`.

    `entries` is the windowed fingerprint list with everything older than
    `_REPEAT_WINDOW_SEC` already dropped; `rules` is the durable per-rule
    aggregate. Malformed rows are discarded individually rather than
    condemning the whole file, so one bad entry cannot reset every count.

    A bare JSON list is the pre-`rules` shape. Reading it as `entries`
    keeps an existing log's debounce working across the upgrade instead
    of silently resetting every count to 1 the first time a refusal is
    recorded by a newer hook.

    Unreadable, absent, or corrupt degrades to `([], {})` — which renders
    exactly today's message — because this only decorates a refusal that
    is being emitted anyway and must never turn one into a crash.
    """
    try:
        with open(path) as f:
            loaded = json.load(f)
    except Exception:
        return [], {}

    raw_entries = loaded.get("entries") if isinstance(loaded, dict) else loaded
    raw_rules = loaded.get("rules") if isinstance(loaded, dict) else None

    entries = []
    if isinstance(raw_entries, list):
        entries = [
            e
            for e in raw_entries
            if isinstance(e, dict)
            and isinstance(e.get("at"), (int, float))
            and now - e["at"] <= _REPEAT_WINDOW_SEC
        ]

    rules = {}
    if isinstance(raw_rules, dict):
        rules = {
            name: agg
            for name, agg in raw_rules.items()
            if isinstance(agg, dict) and isinstance(agg.get("count"), int)
        }

    return entries, rules


def _record_refusal(project_dir, fingerprint, rule=None, now=None):
    """Record a refusal and return `(call_count, rule_count)`, both
    INCLUDING this one. `(1, 1)` means a first refusal on either tier.

    Two tiers, two windows, deliberately. `call_count` counts this exact
    `fingerprint` inside `_REPEAT_WINDOW_SEC` — the retry loop, where the
    agent re-issues a call that was just refused. `rule_count` counts
    `rule` with no time filter at all, because the mistake it exists to
    catch has the opposite shape: it recurs ACROSS sessions, with
    different arguments each time, so no windowed count of identical
    calls can ever see it.

    Durable and bounded at once. The `entries` half keeps its window and
    its cap and stays a debounce hint; the per-rule aggregate is keyed on
    the hook's closed set of rule names, so it is bounded by that set
    rather than by how long the branch lives.

    Best-effort by construction: this only decorates a message that is
    being emitted anyway, so an unreadable or unwritable log must never
    turn a clean refusal into a crash. Every failure path returns
    `(1, 1)`, which renders exactly today's message.
    """
    now = time.time() if now is None else now
    # The scripted-rewrite guard fires before the editor-mode short-circuit,
    # so this runs in non-codeyam repos too. Never CREATE `.codeyam/` as a
    # side effect of refusing something — no project state, no repeat log.
    if not os.path.isdir(os.path.join(project_dir, ".codeyam")):
        return 1, 1
    path = os.path.join(project_dir, _REFUSAL_LOG)
    entries, rules = _load_refusal_log(path, now)

    count = sum(1 for e in entries if e.get("fingerprint") == fingerprint) + 1
    entries.append({"fingerprint": fingerprint, "at": now})

    rule_count = 1
    if rule:
        prior = rules.get(rule)
        rule_count = (prior["count"] if prior else 0) + 1
        rules[rule] = {
            "count": rule_count,
            "firstAt": prior.get("firstAt", now) if prior else now,
            "lastAt": now,
        }

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                {
                    "entries": entries[-_REFUSAL_LOG_MAX:],
                    "rules": _capped_rules(rules),
                },
                f,
            )
    except Exception:
        pass
    return count, rule_count


def _repeat_notice(count, rule_count=1):
    """The line that leads a repeated refusal, or "" on the first one.

    Two tiers, and the exact-call one wins whenever both apply — it is
    both the more specific and the more urgent statement.

    Agents re-issued identical refused calls within seconds — four in a
    row at `backend-journal`. A block that reads the same the second time
    gives no signal that the state has not moved, so the retry looks as
    reasonable as the first attempt. Saying so explicitly is the cheapest
    thing that distinguishes them.

    The second tier catches the shape the first cannot see at all: one
    refusal per session, across sessions, with different arguments each
    time. Measured across 20 build sessions, guardrails refused 16 times
    and `ALREADY REFUSED` rendered ZERO times, while the
    journal-timestamp guard alone fired in five separate sessions. For an
    agent meeting that rule for the first time the accusatory wording
    would simply be false, and reusing it would train agents to discount
    the line — so this tier is informational: the rule is a known
    recurring trap, and the canonical path below is worth reading once
    rather than rediscovering.
    """
    if count >= 2:
        return (
            f"ALREADY REFUSED ({count}x in the last "
            f"{_REPEAT_WINDOW_SEC // 60} minutes): this exact call was refused "
            f"before and nothing has changed since. Re-issuing it will be "
            f"refused again — take the next valid action below instead.\n"
        )
    if rule_count >= _RULE_RECURRENCE_MIN:
        return (
            f"RECURRING GUARDRAIL ({_ordinal(rule_count)} time in this "
            f"project): this rule has blocked a call {rule_count} times here, "
            f"typically once each in a different session — so it is a known "
            f"recurring trap rather than a first encounter. The next valid "
            f"action below is the canonical path; it is worth reading once "
            f"rather than rediscovering.\n"
        )
    return ""


# Read-only explain mode, set ONCE from argv in `main`. Deliberately not an
# environment variable and not an event field: both are reachable from the
# enforcement path, and a verdict channel that the thing being judged can
# switch on is not a diagnostic, it is a bypass. argv belongs to whoever
# invokes the hook, which for a real PreToolUse call is Claude Code itself.
_EXPLAIN_MODE = False


def explain_requested(argv):
    """True when `--explain` appears in `argv`.

    Pure, so the one thing that must never be true during enforcement is
    assertable without running the hook."""
    return "--explain" in argv


def _emit_verdict(verdict, rule, detail, message):
    """Print an explain-mode verdict to STDOUT and exit 0.

    stdout, not stderr, is deliberate: stderr is the enforcement channel Claude
    reads as feedback, and an explain run must be inert there. Exit 0 for the
    same reason — `--explain` answers "what would this do", it never does it."""
    lines = [f"VERDICT: {verdict}"]
    if rule:
        lines.append(f"RULE: {rule}")
    if detail:
        lines.append(f"DETAIL: {detail}")
    if message:
        lines.append(message)
    print("\n".join(lines))
    sys.exit(0)


def allow(reason):
    """Allow the in-flight call — exit 0, silently under enforcement.

    Every allow path in `main` funnels through here so `--explain` can report
    WHICH allow fired. Under enforcement this is exactly `sys.exit(0)`; the
    reason string is never printed, so it costs a normal call nothing."""
    if _EXPLAIN_MODE:
        _emit_verdict("ALLOWED", "", "", reason)
    sys.exit(0)


def notice(rule, message):
    """Let the call through, but say something first — exit 0 with the text on
    stderr.

    The middle verdict between `allow` and `block`, for a call that is safe but
    costs the caller something they should know about. It is deliberately NOT a
    refusal: there is no `Next valid action:` contract to satisfy, because
    nothing needs recovering.

    stderr rather than stdout, and no JSON permission decision: an exit-0 hook
    that prints a `permissionDecision` would also be *granting* permission for
    the call, which is a much bigger claim than "here is a pointer" and would
    silently bypass a prompt the user might otherwise see."""
    if _EXPLAIN_MODE:
        _emit_verdict("NOTICE", rule, "", message)
    print(message, file=sys.stderr)
    sys.exit(0)


def block(project_dir, rule, reason, next_action, reference="", detail="", evidence="", call=""):
    """Emit a phase-gate refusal on the two-line contract and exit 2.

    Every refusal this hook emits goes through here, which is what makes
    `BLOCKED:` / `Next valid action:` an enforced contract rather than a
    documented convention — a new gate cannot ship without a recovery,
    because there is no other way to refuse. `reference` carries material
    the agent may want AFTER it knows what to do (the list of permitted
    slugs, the rationale); it never substitutes for `next_action`.

    `evidence` states what the hook actually OBSERVED — the resolved
    project dir, the file it consulted, expected versus found. It changes
    no verdict. Without it the only way to debug a refusal is to read this
    source, which is what agents did: one spent ~10 tool calls grepping
    this file to discover its own cwd had drifted, a fact the refusal held
    and did not print.

    The repeat fingerprint is `rule` + `detail` + the actual `call` + the
    evidence. Including the call is what stops three DIFFERENT commands
    refused under one rule from escalating to "this exact call was refused
    before" — a false statement that punished an agent for varying its
    approach. Including the evidence resets the counter when the consulted
    state genuinely changed, so a corrective action is no longer scolded as
    a repeat.

    The reason carries a leading `guardrail, not a breakage —` clause because
    the agent is not the only reader. Every one of these refusals is rendered
    into the client's Build tab in red, and a bare `BLOCKED: this pipes a
    gating command into a filter` reads to a watching human as the system
    falling over, when it is in fact the system doing precisely its job. On
    the sessions that were measured, 13 of 71 red results were guardrails
    working exactly as designed. The clause is deliberately INSIDE the reason
    rather than on a line above it, so the `BLOCKED: ` first-token contract
    that agents and `is_recovery_contract` grep for is left untouched.
    """
    message = f"BLOCKED: guardrail, not a breakage — {reason}\nNext valid action: {next_action}"
    if evidence:
        message = f"{message}\nEvidence: {evidence}"
    if reference:
        message = f"{message}\n{reference}"
    if _EXPLAIN_MODE:
        _emit_verdict("BLOCKED", rule, detail, message)
    count, rule_count = _record_refusal(
        project_dir, "\x00".join((rule, detail, call, evidence)), rule
    )
    print(f"{_repeat_notice(count, rule_count)}{message}", file=sys.stderr)
    sys.exit(2)


def resolved_context(project_dir, consulted=""):
    """The evidence prefix every gate can state: where the hook thinks the
    project is, and which file it read to decide.

    `project_dir` falls back to `os.getcwd()` when `CLAUDE_PROJECT_DIR` is
    unset, so a session whose cwd drifted gets judged against the wrong repo
    and never learns why. Printing it makes that one-line obvious."""
    source = "CLAUDE_PROJECT_DIR" if os.environ.get("CLAUDE_PROJECT_DIR") else "os.getcwd()"
    parts = [f"project dir {project_dir} (from {source})"]
    if consulted:
        parts.append(f"consulted {consulted}")
    return "; ".join(parts)


def _test_run_block_message(state, slug, info):
    """Word the test-run block for `slug` from its phase kind.

    Returns a `(reason, next_action)` pair for `block`, which owns the
    two-line rendering. Returning the parts rather than a finished string
    is what keeps this gate on the same contract as every other one.

    `info` is the slug's `noTestSlugs` entry, or None when the cache
    predates that projection (or dropped the entry as malformed).

    Sixteen phases declare `test_scope: none`, but only five of them —
    plan / confirm / prepare / prototype / demo — are actually pre-Demo. The
    rest (final-presentation, journal, pre-commit-sync, commit, push,
    feature-complete) sit AFTER every test-running phase, so telling an
    agent there that hardening "starts at Deconstruct" and to run tests at
    `*-extract-tdd` names a step it has already passed and cannot reach
    without `editor change`. The block is right at both; only the
    explanation and the named recovery differ."""
    where = _slug_label(state, slug)
    if not info or info.get("kind") != "post-hardening":
        # Pre-Demo, or no projection to judge by. This wording is accurate
        # where it applies, and it is the status-quo degrade where the cache
        # cannot say.
        return (
            f"test runs are not allowed at {where} "
            f"(pre-Demo, test_scope: none). The Plan→Demo stretch is for building "
            f"fast and getting working functionality in front of the user — "
            f"hardening (tests, extraction, glossary) starts at Deconstruct.",
            "keep building — run tests at "
            "`ui-extract-tdd` / `backend-extract-tdd`.",
        )
    next_slug = info.get("nextTestRunSlug")
    if next_slug:
        recovery = (
            f"advance to `{next_slug}` — the next step in this mode where "
            f"test runs are in scope."
        )
    else:
        recovery = (
            "advance — no test-running step remains in this mode, so there is "
            "nowhere left to re-run this."
        )
    return (
        f"test runs are not allowed at {where} "
        f"(test_scope: none). The hardening phases already ran the tests; this "
        f"step is a presentation / commit gate, where a test run is out of "
        f"scope.",
        recovery,
    )


def _preview_hint(mode, project_dir):
    """Hint shown when AskUserQuestion is blocked for missing preview.

    Backend mode never has a live preview — point at the results
    panel instead. UI mode points at `editor preview` with the
    user-configured default screen size."""
    cli = cli_command()
    if mode == "backend":
        return f"{cli} editor show-results"
    default_dim = "Desktop"
    editor_config_path = os.path.join(project_dir, ".codeyam", "editor.json")
    try:
        with open(editor_config_path, "r") as f:
            cfg = json.load(f)
        default_dim = cfg.get("defaultScreenSize", "Desktop")
    except Exception:
        pass
    return f'{cli} editor preview \'{{"dimension":"{default_dim}"}}\''


# Stack-agnostic raw test runners, matched by TOKEN SHAPE rather than by a
# regex over the raw command string, so a runner NAME is only a test run when
# it names the program actually being run. A runner name inside a quoted
# argument is data: `editor change "Fix: missing pytest in the VM image"`,
# `git commit -m "add pytest coverage"`, and `python3 -c "print('refresh-tests')"`
# all mention a runner without invoking one, and a whole-string matcher refused
# every one of them. This is the same command-position discipline
# `_has_inplace_editor` and `_uses_pcre_grep` use — see `_in_command_position`
# and `_split_commands`, defined with the scripted-rewrite guard below.
#
# Runners invoked by bare name: `pytest tests/`, `jest`, `vitest run`.
_TEST_RUNNER_PROGRAMS = frozenset(("pytest", "jest", "vitest"))
# Runners that are a program plus a subcommand — `cargo build` is not a test
# run, `cargo test` is.
_TEST_RUNNER_SUBCOMMANDS = {
    "cargo": frozenset(("test", "nextest")),
    "go": frozenset(("test",)),
}
# `python3 -m pytest` — the module names the runner, not the interpreter. Any
# `python`/`python3`/`python3.12` spelling counts.
_PYTHON_INTERPRETER = re.compile(r"^python[0-9.]*$")
# `refresh-tests` is codeyam's own test command — the one the workflow actually
# uses — and is always a test run when it is the CLI's VERB. As an argument to
# some other verb it is a feature title or a search string, not a run.
_CODEYAM_CLIS = frozenset(("codeyam-editor", "codeyam-editor-dev"))
_CODEYAM_TEST_VERBS = frozenset(("refresh-tests",))
# Shells that run a script named as their argument, so a configured test script
# reached through one is still an invocation of it.
_SCRIPT_INTERPRETERS = frozenset(("bash", "sh", "zsh", "ksh", "dash"))


def _configured_test_scripts(project_dir):
    """Project-specific test-runner SCRIPT invocations derived from
    `testRunners[].command` in editor.json — e.g. `bash scripts/run-shell-tests.sh`.

    Lets the gate catch a raw run of the project's OWN test script, not just
    the stack-agnostic runners above, so the gate is config-aware rather than a
    fixed hardcoded list. Only tokens that look like a script path (`scripts/…`
    or ending in `.sh`) are lifted — that deliberately skips a bare interpreter
    like `python3` in `python3 -m pytest`, which `_invokes_test_runner` already
    covers and which would over-block if treated as a runner."""
    cfg_path = os.path.join(project_dir, ".codeyam", "editor.json")
    scripts = []
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
    except Exception:
        return scripts
    for runner in cfg.get("testRunners", []) or []:
        cmd = runner.get("command", "") if isinstance(runner, dict) else ""
        for tok in cmd.split():
            if tok.startswith("scripts/") or tok.endswith(".sh"):
                scripts.append(tok)
    return scripts


def _leading_operand(tokens):
    """The first token that is a subcommand rather than an option — the `test`
    in `cargo +nightly test -p codeyam-types`. None when there is none."""
    for tok in tokens:
        if tok.startswith("-") or tok.startswith("+"):
            continue
        return tok
    return None


def _module_target(tokens):
    """The module an interpreter's `-m` flag runs — `pytest` in
    `python3 -m pytest tests/`. None when there is no `-m`."""
    for index, tok in enumerate(tokens):
        if tok == "-m" and index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def _codeyam_verb(tokens):
    """The subcommand verb of a codeyam CLI invocation, skipping options and the
    `editor` subcommand group — `refresh-tests` in `codeyam-editor editor
    refresh-tests --changed`, but `change` in `codeyam-editor editor change
    "Fix: missing pytest in the VM image"`. None when there is no verb."""
    for tok in tokens:
        if tok.startswith("-") or tok == "editor":
            continue
        return tok
    return None


def _invokes_test_runner(tokens):
    """True when the program in command position of one already-split command is
    a test runner, in any of the shapes a runner is actually invoked through:
    bare name, program + subcommand, interpreter + module, or codeyam CLI verb.

    Blind to quoted text by construction — `shlex` has already collapsed each
    quoted region into a single token, so a runner name inside a feature title,
    a commit message, or a string literal can never be the program."""
    for index, tok in enumerate(tokens):
        if not _in_command_position(tokens, index):
            continue
        program = _program_name(tok)
        rest = tokens[index + 1:]
        if program in _TEST_RUNNER_PROGRAMS:
            return True
        if _leading_operand(rest) in _TEST_RUNNER_SUBCOMMANDS.get(program, ()):
            return True
        if _PYTHON_INTERPRETER.match(program) and _module_target(rest) in _TEST_RUNNER_PROGRAMS:
            return True
        if program in _CODEYAM_CLIS and _codeyam_verb(rest) in _CODEYAM_TEST_VERBS:
            return True
    return False


def _shell_c_payload(tokens):
    """The command string a shell is asked to run — `pytest tests/` in
    `bash -c "pytest tests/"`. None when this is not a `-c` invocation.

    Tokenizing alone would read that payload as one opaque argument and let a
    real test run through, so the payload is re-scanned as a command in its own
    right. This is the one place a quoted string IS an invocation."""
    for index, tok in enumerate(tokens):
        if _program_name(tok) not in _SCRIPT_INTERPRETERS:
            continue
        if not _in_command_position(tokens, index):
            continue
        rest = tokens[index + 1:]
        for offset, arg in enumerate(rest):
            if arg == "-c" and offset + 1 < len(rest):
                return rest[offset + 1]
    return None


def _program_name(token):
    """A token reduced to the name it is compared on, so a path-qualified
    invocation matches its bare spelling — `/usr/bin/pytest` is `pytest`, and a
    configured `scripts/run-shell-tests.sh` matches `./scripts/run-shell-tests.sh`."""
    return token.rsplit("/", 1)[-1]


def _invokes_configured_script(tokens, project_dir):
    """True when one of the project's configured test scripts is what this
    command runs — in command position (`./scripts/run-shell-tests.sh`) or as the
    script argument of a shell (`bash scripts/run-shell-tests.sh`).

    Comparing whole tokens is what keeps `git commit -m "fixes
    scripts/run-shell-tests.sh"` allowed: a quoted message is one token, and one
    token is never equal to the script path inside it."""
    scripts = {_program_name(s) for s in _configured_test_scripts(project_dir)}
    if not scripts:
        return False
    for index, tok in enumerate(tokens):
        if _program_name(tok) not in scripts:
            continue
        if _in_command_position(tokens, index):
            return True
        if _program_name(tokens[index - 1]) in _SCRIPT_INTERPRETERS:
            return True
    return False


def is_test_run_command(command, project_dir):
    """True iff `command` invokes a test run — a common raw runner, codeyam's own
    `refresh-tests`, or the project's configured test script.

    Scoped to one command at a time, so a runner in one segment says nothing
    about the next. Fails closed: a command that cannot be tokenized counts as a
    test run, so a malformed quote is never an evasion path — the same contract
    `_has_inplace_editor` and `_uses_pcre_grep` carry."""
    for segment in _split_commands(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            return True
        if _invokes_test_runner(tokens):
            return True
        if _invokes_configured_script(tokens, project_dir):
            return True
        payload = _shell_c_payload(tokens)
        if payload is not None and is_test_run_command(payload, project_dir):
            return True
    return False


# --- Scripted source-rewrite guard -----------------------------------------
#
# CLAUDE.md bans machine-rewriting tracked source ("never a `python`/regex/
# brace-matching find-and-replace … such scripts parse the language with the
# wrong grammar and self-match the code they just generated"). Documentation
# alone did not hold, so this guard turns the guideline into a refusal that
# names the sanctioned alternatives.
#
# The signature is the SHAPE, not the interpreter: a shell command that both
# computes a text transform in-process AND lands it on a git-tracked source
# file. Inspecting JSON state, running a committed script, and writing to a
# temp/untracked path all stay allowed.

# Suffixes whose files a reviewer reads as a diff, and which must therefore be
# edited with the Edit tool rather than machine-rewritten. Deliberately broad
# and additive across stacks: a language absent from this list is simply not
# guarded, so an unlisted extension degrades to "allow", never to a spurious
# block. `.json` is omitted on purpose — rewriting JSON through a parser is
# structurally sound and is how config edits are legitimately scripted.
SOURCE_SUFFIXES = (
    ".rs", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".rb", ".go",
    ".java", ".kt", ".swift", ".m", ".mm", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".php", ".ex", ".exs", ".sh", ".bash", ".zsh", ".ps1", ".sql",
    ".svelte", ".vue", ".astro", ".css", ".scss", ".html", ".md", ".toml",
    ".yaml", ".yml",
)

# Bound the git query so a pathological command cannot spawn a huge argv.
_MAX_PATH_CANDIDATES = 40

# A pathspec we are willing to hand to `git ls-files`. Excludes whitespace and
# `:` (git's pathspec-magic prefix) so an odd token cannot change git's parse.
_PATHSPEC_SAFE = re.compile(r"^[A-Za-z0-9_./*+-]+$")

_OPEN_CALL = re.compile(r"\bopen\s*\(")
# `Path("x").write_text(` yields its literal; a bare `p.write_text(` does not.
_WRITE_TEXT = re.compile(
    r"""(?:Path\s*\(\s*(?P<q>['"])(?P<path>[^'"]+)(?P=q)\s*\)\s*)?\.write_(?:text|bytes)\s*\("""
)
_NODE_WRITE = re.compile(
    r"""writeFile(?:Sync)?\s*\(\s*(?:(?P<q>['"`])(?P<path>[^'"`]+)(?P=q))?"""
)
# `> path` / `>> path`, but not the fd forms (`2>&1`, `>&2`).
_SHELL_REDIRECT = re.compile(r"""(?<![0-9&])>>?\s*(?P<path>[^\s;|&<>()'"]+)""")
# Anything shaped like a path with an extension, wherever it appears. Matching
# the shape directly rather than tokenizing by quotes or whitespace is what
# makes the fallback survive nested quoting — a one-liner like
# `python3 -c "p = 'src/lib.rs'; …"` yields no clean quoted or whitespace token,
# because the inner quotes interleave with the outer ones.
_PATHLIKE = re.compile(r"/?[A-Za-z0-9_][A-Za-z0-9_./*+-]*\.[A-Za-z0-9]+")
# An in-place flag for sed/perl: `-i`, `-i.bak`, `-pi`, `--in-place`. The
# pre-`i` letter class excludes `e`/`E`/`I` so perl's `-Ilib` (a library path,
# not an in-place edit) does not false-match.
_INPLACE_FLAG = re.compile(r"^(?:--in-place(?:=.*)?|-[a-df-hj-zA-DF-HJ-Z0-9]*i.*)$")
# Unquoted characters that end one command and begin another. `||` and `&&` are
# runs of these, so splitting per-character yields an empty middle segment that
# is simply dropped. `(`/`)`/backtick are boundaries too, so a subshell or a
# command substitution is scanned as its own command rather than as an argument.
_COMMAND_SEPARATORS = ";|&\n()`"
# Tokens that may precede a program without changing which program runs, so an
# in-place edit reached through one is still an in-place edit. `find … -exec sed
# -i … {} \;` and `xargs sed -i …` are the most natural ways to rewrite a tree
# in bulk; requiring `sed` to be literally first would have unblocked them.
_COMMAND_PREFIXES = frozenset(
    (
        "sudo", "env", "xargs", "time", "nohup", "command", "exec", "nice",
        "ionice", "stdbuf", "-exec", "-execdir", "then", "do", "else", "{",
        # `npx vitest run` runs `vitest` — the launcher resolves the binary
        # without changing which program it is.
        "npx",
    )
)
# `LC_ALL=C sed -i …` — a leading assignment is a prefix, not the program.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# grep short options that consume the rest of their cluster as a value, so a
# `P` following one is that value (`grep -eP` searches for the text "P") rather
# than the PCRE flag.
_GREP_VALUE_FLAGS = frozenset("efmABCDd")

# The `codeyam-editor editor` subcommands that may not be piped into a filter.
# Keep in sync with the CLAUDE.md "CLI error conventions" section, under "Do not
# pipe gating or long-running `codeyam-editor` commands through `tail` / `grep`
# / `head`".
#
# Deliberately NOT every subcommand. The rule's rationale is about what a pipe
# destroys, so it covers the commands that have something to lose. Three of the
# four are properties of the command's own output — a meaningful exit code, a
# liveness heartbeat, and a tail-safe completion trailer — which is what the
# gates whose exit code is a verdict and the long ones that heartbeat while they
# run all carry. Piping a small read-only query (`registry-query … | jq .`)
# loses nothing, and refusing it would make the rule feel arbitrary rather than
# earned.
#
# The fourth is stronger and is why the `preview` family is listed: a SIDE
# EFFECT A LATER GATE DEPENDS ON. `preview`, `preview-flow`, `preview-html`,
# `preview-interact`, `preview-verify`, and `show-results` each write the
# preview-shown marker
# (`.codeyam/preview-shown.json`) that `present-interactive` reads before it will
# allow an `AskUserQuestion`. A downstream `head -1` closes the pipe and SIGPIPEs
# the process mid-command, so the loss is invisible: the capture succeeds, the
# screenshots are correct, the body reports `success=true`, and only the gate
# stays shut. That cost five VM-13 sessions a wall each. The marker write now
# precedes every stdout write in those commands, which makes the loss
# unreachable — this entry is defense in depth, not the fix. `preview-nav`
# writes no marker; it rides along so the rule is "don't pipe the preview
# family" rather than an exception nobody will remember. `preview-show` writes
# none either, and that one is deliberate rather than incidental: it is
# read-only on the live pane (it broadcasts no nav and captures nothing), so it
# reports where a preview WOULD render without ever rendering one — marking off
# it would open the gate on a frame no user ever saw.
# `preview_gate::marker_writing_command_sources()` is the enforced twin of this
# enumeration; a new writer must join both.
_GATING_SUBCOMMANDS = frozenset(
    (
        "advance",
        "analyze-imports",
        "audit",
        # The two terminal steps. Neither is slow in the ordinary case, and that
        # is exactly why they belong here: each POSTs to a handler that shells
        # out to git, so each CAN block, and each is the LAST command of its
        # flow — so a block strands the whole cycle with nothing left to report
        # it. Unwrapped, `feature-complete` hung for ten minutes emitting no
        # heartbeat and no status document, which is indistinguishable from
        # working. Membership here is what buys the liveness signal.
        "feature-complete",
        "plan-complete",
        "pre-commit-sync",
        "preview",
        "preview-flow",
        "preview-html",
        "preview-interact",
        "preview-nav",
        "preview-verify",
        "push",
        "reconcile-registry",
        "refresh-tests",
        "scenario-matrix",
        "scenario-taxonomy",
        "session-checkpoint",
        "session-finalize",
        "show-results",
        "verify-build",
        "verify-full-finalize",
        "verify-test-cache",
    )
)
# A `codeyam-editor editor <subcommand>` invocation with its subcommand
# captured. Used only as the fail-closed fallback for a stage `shlex` cannot
# tokenize; the tokenizing path in `_gating_subcommand` is position-aware and
# is what runs normally.
_GATING_INVOCATION = re.compile(
    r"\bcodeyam-editor(?:-dev)?\s+editor\s+([a-z][a-z0-9-]*)"
)
# `--help` / `-h` as a standalone argument. A help text has no exit code to
# lose, no heartbeat, and no completion trailer, so piping one is harmless.
_HELP_FLAG = re.compile(r"(?:^|\s)(?:--help|-h)(?=\s|$)")


def _string_literal(expr):
    """The inner text of `expr` when it is a single quoted string literal."""
    expr = expr.strip()
    if len(expr) >= 2 and expr[0] == expr[-1] and expr[0] in "'\"`":
        inner = expr[1:-1]
        if expr[0] not in inner:
            return inner
    return None


def _call_args(text, paren_index):
    """Top-level, comma-separated argument expressions of the call whose `(`
    sits at `paren_index`. Quote-aware so a comma or paren inside a string
    literal does not split an argument. Returns [] if the parens never close."""
    depth = 0
    quote = ""
    args = []
    current = []
    for i in range(paren_index, len(text)):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
            current.append(ch)
            continue
        if ch in "'\"`":
            quote = ch
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
            if depth == 1:
                continue
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(current))
                return args
        if depth == 1 and ch == ",":
            args.append("".join(current))
            current = []
        else:
            current.append(ch)
    return []


def _is_redirection_ampersand(chars, index):
    """True when the `&` at `chars[index]` is part of a REDIRECTION rather than
    a command boundary — `2>&1`, `>&2`, `&>out`.

    `&` is a separator character, so without this the single most common way to
    capture a command's stderr splits it in two: `… --auto-apply 2>&1 | tail`
    tokenizes as `… 2>` and `1 | tail`, putting the command and its filter in
    different pipelines. That is exactly the shape of every observed violation
    of the no-piping rule, so it is the shape the rule most has to see."""
    if chars[index] != "&":
        return False
    if index > 0 and chars[index - 1] in "><":
        return True
    return index + 1 < len(chars) and chars[index + 1] == ">"


# Programs whose heredoc body is DATA — a message, a document, a patch — and
# never a program. Only these have their bodies elided.
#
# An allowlist, not a denylist, because the two directions fail differently. A
# body fed to `python3 - <<'EOF'` IS the program: eliding it hides the exact
# incidents the scripted-rewrite guard was built from (a heredoc that read a
# tracked `.rs` file, ran `str.replace`, and wrote it back). A body fed to
# `git commit -F -` is prose the shell never lexes. Guessing wrong about an
# unknown program costs a false positive one way and an evasion path the
# other, so the unknown program keeps its body.
_HEREDOC_DATA_CONSUMERS = frozenset(
    (
        "cat", "tee", "git", "mail", "mailx", "sendmail", "wc", "sort", "uniq",
        "head", "tail", "column", "tr", "jq", "less", "more", "diff", "patch",
        "md5sum", "sha256sum", "base64", "gpg", "curl", "wget",
    )
)


def _heredoc_consumer(prefix):
    """The program that will consume the heredoc opened at the end of `prefix`
    — `git` in `git commit -F - <<'EOF'`, `python3` in `python3 - <<'EOF'`.

    Scans back to the last unquoted separator so only the CURRENT command is
    considered, then skips the wrappers and leading assignments that do not
    change which program runs. Deliberately does not reuse `_split_commands`:
    that routes through `elide_heredoc_bodies`, and calling it from inside the
    elision would be mutual recursion."""
    boundary = -1
    quote = ""
    escaped = False
    for index, ch in enumerate(prefix):
        if escaped:
            escaped = False
        elif ch == "\\" and quote != "'":
            escaped = True
        elif quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in _COMMAND_SEPARATORS:
            boundary = index
    for tok in prefix[boundary + 1:].split():
        if tok in _COMMAND_PREFIXES or _ASSIGNMENT.match(tok):
            continue
        return _program_name(tok)
    return ""


def _heredoc_openers(line):
    """The heredocs `line` opens, as `(delimiter, strip_tabs, elide)` triples in
    the order the shell will consume their bodies.

    `elide` is False when the consuming program EXECUTES the body rather than
    reading it as data — see `_HEREDOC_DATA_CONSUMERS`. Such a body is still
    tracked here, because the hook must know where the heredoc ends to resume
    scanning correctly on the line after it; it is simply kept rather than
    dropped.

    Quote-aware, so a literal `<<` inside a string is not an opener. `<<<` is a
    here-STRING — its operand is the data itself, on the same line, with no body
    to elide — so it is skipped rather than mistaken for a heredoc."""
    openers = []
    quote = ""
    escaped = False
    index = 0
    while index < len(line):
        ch = line[index]
        if escaped:
            escaped = False
        elif ch == "\\" and quote != "'":
            escaped = True
        elif quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "<" and line[index + 1:index + 2] == "<":
            if line[index + 2:index + 3] == "<":
                index += 3
                continue
            cursor = index + 2
            strip_tabs = line[cursor:cursor + 1] == "-"
            if strip_tabs:
                cursor += 1
            while cursor < len(line) and line[cursor] in " \t":
                cursor += 1
            if line[cursor:cursor + 1] == "\\":
                cursor += 1
            delimiter, cursor = _heredoc_delimiter(line, cursor)
            if delimiter:
                consumer = _heredoc_consumer(line[:index])
                openers.append(
                    (delimiter, strip_tabs, consumer in _HEREDOC_DATA_CONSUMERS)
                )
            index = cursor
            continue
        index += 1
    return openers


def _heredoc_delimiter(line, cursor):
    """The delimiter word starting at `cursor`, plus the index just past it.

    Handles the three spellings the shell accepts — `'EOF'`, `"EOF"`, and a
    bare `EOF`. The quoting only controls whether the BODY is expanded, which
    is irrelevant here: either way the body is data the shell never lexes as
    commands, which is the whole reason it is elided."""
    opener = line[cursor:cursor + 1]
    if opener in "'\"":
        end = line.find(opener, cursor + 1)
        if end == -1:
            return ("", len(line))
        return (line[cursor + 1:end], end + 1)
    end = cursor
    while end < len(line) and (line[end].isalnum() or line[end] in "_-."):
        end += 1
    return (line[cursor:end], end)


def elide_heredoc_bodies(command):
    """`command` with every heredoc BODY removed, leaving the line that opens it
    — redirects and all — intact.

    A heredoc body is data by shell semantics, exactly as a quoted argument is,
    and this hook already honours the latter. Without this, a commit message
    piped through `git commit -F - <<'EOF'` was lexed as shell: a backticked
    code span in the prose became a command (`` `sed -i` `` read as a scripted
    rewrite, `` `grep -P` `` as a portability violation, `` `cargo test` `` as a
    test run), and a single apostrophe opened an unterminated quote that failed
    four guards closed at once — refusing a commit whose message merely NAMED a
    source file as a machine-rewrite of it.

    Eliding the body rather than relaxing the tokenizer is the point: the
    fail-closed contract on a malformed quote stays exactly as strict, because
    a body the shell never lexes was never the tokenizer's input to begin with.
    The opening line SURVIVES, so `cat <<'EOF' > src/lib.rs` still trips the
    scripted-rewrite guard on its redirect, and `git commit -F - <<'EOF'` is
    still a `git commit`.

    And only a DATA consumer's body is elided. `python3 - <<'EOF'` executes its
    body, so that body is a program and is kept — eliding it would have blinded
    the scripted-rewrite guard to the very incidents it was built from."""
    if "<<" not in command:
        return command
    kept = []
    pending = []
    for line in command.split("\n"):
        if pending:
            delimiter, strip_tabs, elide = pending[0]
            candidate = line.lstrip("\t") if strip_tabs else line
            if candidate.rstrip() == delimiter:
                pending.pop(0)
            if not elide:
                kept.append(line)
            continue
        kept.append(line)
        pending.extend(_heredoc_openers(line))
    return "\n".join(kept)


def _split_commands_with_separators(command):
    """`command` split at unquoted shell separators, as `(segment, separator)`
    pairs — the separator being the character that ENDED the segment, or `""`
    for the final one.

    Heredoc bodies are elided first (`elide_heredoc_bodies`) — this is the one
    seam every command-scanning guard passes through, so eliding here is what
    makes the whole hook heredoc-aware rather than each predicate separately.

    Quote-aware: a separator inside `'…'` or `"…"` is data — a grep pattern, not
    a boundary — and a backslash escapes the next character outside single
    quotes, so `find … {} \\;` does not split at its terminator. Every character
    is preserved verbatim within its segment, including the quotes, so an
    unterminated quote survives into the segment and is caught downstream.

    Empty segments are KEPT here, unlike in `_split_commands`. `||` and `&&`
    are runs of separator characters, so they yield an empty middle segment,
    and that emptiness is exactly what distinguishes `a || b` from the pipe
    `a | b` for `_pipelines`. Callers that only want the commands use
    `_split_commands`, which drops them."""
    pairs = []
    current = []
    quote = ""
    escaped = False
    chars = list(elide_heredoc_bodies(command))
    for index, ch in enumerate(chars):
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\" and quote != "'":
            current.append(ch)
            escaped = True
        elif quote:
            current.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            current.append(ch)
            quote = ch
        elif ch in _COMMAND_SEPARATORS and not _is_redirection_ampersand(chars, index):
            pairs.append(("".join(current), ch))
            current = []
        else:
            current.append(ch)
    pairs.append(("".join(current), ""))
    return pairs


def _split_commands(command):
    """`command` split into individual commands at unquoted shell separators.

    The non-empty segments of `_split_commands_with_separators` — one scanner
    serves both, so the quote handling that keeps `grep -rn "grep -P"` from
    self-matching cannot drift between the two."""
    return [segment for segment, _ in _split_commands_with_separators(command)
            if segment.strip()]


def _in_command_position(tokens, index):
    """True when `tokens[index]` is the program a command runs rather than one
    of its arguments — allowing for the wrappers and leading environment
    assignments that still run it (`sudo sed`, `find … -exec sed`, `LC_ALL=C
    sed`). This is what keeps `grep -rn sed -i crates/` — where `sed` is a
    search term — from reading as an in-place edit."""
    if index == 0:
        return True
    prior = tokens[index - 1]
    return prior in _COMMAND_PREFIXES or bool(_ASSIGNMENT.match(prior))


def _has_inplace_editor(command):
    """True iff `command` invokes `sed`/`perl` with an in-place flag.

    Scoped to one command and blind to quoted text. A `sed` in one command says
    nothing about a flag in the next, so the scan restarts at every separator;
    and quoted regions collapse into single tokens, so a `-i` inside a grep
    pattern is data. Fails closed: a command that cannot be tokenized counts as
    an in-place edit, so a malformed quote is never an evasion path."""
    for segment in _split_commands(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            return True
        for index, tok in enumerate(tokens):
            if tok.rsplit("/", 1)[-1] not in ("sed", "perl"):
                continue
            if not _in_command_position(tokens, index):
                continue
            if any(_INPLACE_FLAG.match(t) for t in tokens[index + 1:]):
                return True
    return False


def _is_pcre_flag(token):
    """True when `token` is grep's PCRE flag in any spelling GNU accepts: `-P`,
    a short cluster containing it (`-Pn`, `-rP`, `-Pio`), or `--perl-regexp`
    and the unambiguous abbreviations of it (`--perl`, `--perl-reg`). A cluster
    stops at the first value-taking letter, so `-eP` is a search for "P"."""
    if token.startswith("--"):
        return len(token) >= len("--perl") and "--perl-regexp".startswith(token)
    if not token.startswith("-") or token == "-":
        return False
    for ch in token[1:]:
        if ch == "P":
            return True
        if ch in _GREP_VALUE_FLAGS:
            return False
    return False


def _uses_pcre_grep(command):
    """True iff `command` invokes `grep` with a PCRE flag.

    Scoped to one command and blind to quoted text, for the same reason as
    `_has_inplace_editor`: the flag is only a flag when it is an argument of an
    actual `grep` invocation. That keeps `grep -rn "grep -P" .claude/` — where
    the flag is the search term — and `echo 'do not use grep -P'` from reading
    as PCRE use. `git grep -P` is excluded because `grep` is not in command
    position there, and git's own PCRE support is portable across both hosts.
    Fails closed: a command that cannot be tokenized counts as a match, so a
    malformed quote is never an evasion path."""
    for segment in _split_commands(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            return True
        for index, tok in enumerate(tokens):
            if tok.rsplit("/", 1)[-1] != "grep":
                continue
            if not _in_command_position(tokens, index):
                continue
            if any(_is_pcre_flag(t) for t in tokens[index + 1:]):
                return True
    return False


# git's own options that CONSUME the next argument, so the token after one is a
# value rather than the subcommand. Without this, `git -C /path commit` reads
# `/path` as the subcommand and the commit gate never fires.
_GIT_VALUE_OPTIONS = frozenset(
    (
        "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
        "--super-prefix", "--config-env",
    )
)


def _git_subcommand(rest):
    """The subcommand of a `git` invocation — `commit` in `git -C /repo commit
    -m x`. None when the invocation names no subcommand."""
    skip = False
    for tok in rest:
        if skip:
            skip = False
            continue
        if tok in _GIT_VALUE_OPTIONS:
            skip = True
            continue
        if tok.startswith("-"):
            continue
        return tok
    return None


def invokes_git_subcommand(command, subcommand):
    """True iff `command` actually RUNS `git <subcommand>`.

    Replaces a bare `"git commit" in command` substring test, which read any
    MENTION of the verb as an invocation: `echo "remember to git commit later"`
    was refused, and so was a commit whose own message discussed committing.
    Position-aware for the same reason `_uses_pcre_grep` is — the name is only
    an invocation when it is the program being run, and `shlex` has already
    collapsed every quoted region into one token, so a verb inside a message can
    never be it.

    A shell payload is re-scanned as a command in its own right, so
    `bash -c "git commit -m x"` is still a commit. Fails closed: a stage that
    cannot be tokenized counts as a match, the same contract every other guard
    here carries."""
    for segment in _split_commands(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            return True
        for index, tok in enumerate(tokens):
            if _program_name(tok) != "git" or not _in_command_position(tokens, index):
                continue
            if _git_subcommand(tokens[index + 1:]) == subcommand:
                return True
        payload = _shell_c_payload(tokens)
        if payload is not None and invokes_git_subcommand(payload, subcommand):
            return True
    return False


# The `codeyam-editor:editor` spelling reaches the same CLI through the plugin
# invocation form, so it is one token rather than a program plus a subcommand.
# Derived from _CODEYAM_CLIS rather than spelled out. commands::apply_cli_name
# rewrites the canonical plugin-form token into the dev-wrapper one at install
# time, so a hardcoded pair collapses to a single element on a -dev install and
# recognition of the canonical spelling is silently lost. Deriving the set keeps
# the CLI-name list single-sourced, survives that rewrite, and leaves no
# non-canonical literal for the SHIPPED_AGENT_FILE_NONCANONICAL_CLI_NAME audit
# invariant to flag — which is why this file needs no allowlist entry.
_CODEYAM_EDITOR_TOKENS = frozenset(f"{cli}:editor" for cli in _CODEYAM_CLIS)


def invokes_codeyam_editor(command):
    """True iff `command` actually RUNS a `codeyam-editor editor …` subcommand.

    This one gates an ALLOW, not a refusal, which is why it had to change: the
    substring test it replaces short-circuited the commit, push, code-change and
    PCRE gates for any command whose TEXT contained the CLI name anywhere —
    including inside a quoted commit message. `git commit -m "chore: document
    codeyam-editor editor advance"` was allowed at every slug. Closing that is
    the same substring-versus-structure fix as `invokes_git_subcommand`, applied
    in the opposite direction.

    Fails closed the way an allow must: a stage that cannot be tokenized does
    NOT earn the bypass, so a malformed quote can never buy one."""
    for segment in _split_commands(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            continue
        for index, tok in enumerate(tokens):
            if not _in_command_position(tokens, index):
                continue
            if _program_name(tok) in _CODEYAM_EDITOR_TOKENS:
                return True
            if _program_name(tok) not in _CODEYAM_CLIS:
                continue
            rest = tokens[index + 1:]
            if rest and rest[0] == "editor":
                return True
    return False


def _pipelines(command):
    """`command` grouped into pipelines — each a list of the stages joined by
    unquoted `|`, in order.

    A lone command is a one-stage pipeline, so `len(stages) > 1` is exactly the
    "this was piped" test. `||` is NOT a pipe: it is two separator characters,
    so it yields an empty middle segment, and an empty segment ends the current
    pipeline rather than extending it. That empty-segment check is the whole
    difference between `audit || echo failed` (allowed — two pipelines) and
    `audit | tail` (one two-stage pipeline)."""
    pipelines = []
    current = []
    pairs = _split_commands_with_separators(command)
    for index, (segment, separator) in enumerate(pairs):
        if not segment.strip():
            if current:
                pipelines.append(current)
                current = []
            continue
        current.append(segment)
        piped_into_next = (
            separator == "|"
            and index + 1 < len(pairs)
            and pairs[index + 1][0].strip()
        )
        if not piped_into_next:
            pipelines.append(current)
            current = []
    if current:
        pipelines.append(current)
    return pipelines


def _gating_subcommand(stage):
    """The gating `codeyam-editor editor <subcommand>` that `stage` RUNS, or
    None.

    Position-aware for the same reason `_uses_pcre_grep` is: the name is only
    an invocation when it is the program the stage runs, so
    `grep "codeyam-editor editor audit" notes.md | head` — where it is a search
    term — does not trip the rule. Fails closed: a stage that cannot be
    tokenized falls back to the position-blind regex, so a malformed quote is
    never an evasion path."""
    try:
        tokens = shlex.split(stage, posix=True)
    except ValueError:
        match = _GATING_INVOCATION.search(stage)
        return match.group(1) if match else None
    for index, tok in enumerate(tokens):
        if tok.rsplit("/", 1)[-1] not in ("codeyam-editor", "codeyam-editor-dev"):
            continue
        if not _in_command_position(tokens, index):
            continue
        rest = tokens[index + 1:]
        if len(rest) >= 2 and rest[0] == "editor" and rest[1] in _GATING_SUBCOMMANDS:
            return rest[1]
    return None


def _is_tee_stage(stage):
    """True when `stage` is a `tee` — the one downstream stage that preserves
    what a pipe would otherwise destroy. `tee` copies stdout to a file and
    passes it through unchanged, and a pipeline ending in `tee` reports `tee`'s
    status, which fails only on a write error. So the exit code, the heartbeat,
    and the completion trailer all survive."""
    try:
        tokens = shlex.split(stage, posix=True)
    except ValueError:
        return False
    return bool(tokens) and tokens[0].rsplit("/", 1)[-1] == "tee"


def _capture_available():
    """True when the liveness bracket's stream capture is available on this
    host, which is what makes piping a gating command lossless.

    The capture is Unix descriptor surgery (`stream_capture.rs`, `#[cfg(unix)]`).
    Elsewhere `TranscriptGuard::install` returns `None`, so a piped command
    writes straight to the caller's pipe: its `println!` sites see EPIPE, panic,
    and the run dies mid-flight with no transcript and no status document to
    recover from. On those hosts the old refusal is still the right answer."""
    return os.name == "posix"


def piped_gating_command(command):
    """The gating subcommand `command` pipes into a filter, or None.

    This is the mechanical form of the CLAUDE.md "do not pipe gating or
    long-running commands" rule. The rule is documented at length and violated
    anyway, on the very commands it names — so it is enforced here rather than
    left to prose.

    Three properties of a wrapped gating command die at a pipe. The shell
    reports the LAST stage's status, so `verify-build | tail` exits 0 when the
    build failed — a false green that advances the workflow past a failing
    gate. `tail`/`grep` block-buffer to EOF, so a still-running command's output
    and its `CODEYAM_CMD_RUNNING` heartbeat never surface and the read looks
    empty. And the tail-safe completion trailer — the `EXACT_TASK_TITLE`
    hand-off and the `CODEYAM_CMD_COMPLETE` sentinel — gets sliced off.

    Only `tee` is exempt, because only `tee` rescues all three: it copies stdout
    to a file and passes it through unchanged, so the exit code, the heartbeat,
    and the trailer all survive. `set -o pipefail` and `${PIPESTATUS[0]}` rescue
    the exit code ALONE and were previously honoured as full exemptions — which
    let a `reconcile-registry … 2>&1 | tail -30` through on the strength of a
    `PIPESTATUS` echo and cost the session ten minutes staring at a
    block-buffered pipe. `--help` is exempt because a help text has no exit code
    to lose, no heartbeat, and no trailer."""
    for stages in _pipelines(command):
        for index, stage in enumerate(stages[:-1]):
            subcommand = _gating_subcommand(stage)
            if subcommand is None or _HELP_FLAG.search(stage):
                continue
            if all(_is_tee_stage(later) for later in stages[index + 1:]):
                continue
            return subcommand
    return None


def piped_gating_notice(subcommand):
    """The advisory text for a piped gating command — allowed, not refused.

    The pipe used to be refused because it destroyed four things. Three are now
    recovered from disk and the fourth cannot happen: every subcommand in
    `_GATING_SUBCOMMANDS` runs inside the liveness bracket, where stdout is a
    pipe the command's own process owns, so a departed filter can no longer
    SIGPIPE it mid-run. What a pipe still costs is the terminal DISPLAY, the
    shell-level exit code, and — when the run is auto-backgrounded — the
    COMPLETION NOTIFICATION. This names where each was written instead.

    That third cost is the one this notice used to get wrong, by claiming a
    pipe cost "exactly two things". A filter that outlives the command holds the
    pipeline open, so the harness task never exits and no notification is ever
    going to fire; the command meanwhile finished and wrote its verdict.
    Observed 2026-08-23 on a `session-checkpoint` piped through `grep | tail`:
    verdict on disk in 343s, agent still waiting hours later, because "no
    notification yet" is indistinguishable from "still running" unless something
    says otherwise. The root leak that produced it is fixed, but any long-lived
    process the command leaves behind can hold a pipe open, so the agent still
    needs to know the verdict does not depend on the notification.

    Saying it at all — rather than allowing silently — is the point. The
    pipeline's `$?` is the filter's, and an agent that reads it will believe a
    failed gate passed. The notice has to arrive BEFORE the command runs,
    because afterwards the misleading exit code is already in hand."""
    return (
        f"NOTE: `{cli_command()} editor {subcommand}` is piped into a filter. "
        f"That is allowed — the command runs to completion and every side "
        f"effect lands — but your shell reports the FILTER's exit code, not the "
        f"command's, so do not read `$?` as the verdict.\n"
        f"  Real verdict: .codeyam/state/command-output/{subcommand}.status.json "
        f"(the `status` field — the same document the "
        f"`CODEYAM_CMD_COMPLETE` line carries). Authoritative the moment the "
        f"command finishes, whether or not a notification ever arrives.\n"
        f"  Full output:  .codeyam/state/command-output/{subcommand}.txt "
        f"(complete stdout + stderr, unsliced).\n"
        f"  Still alive?  a backgrounded run's one-line `.heartbeat` sidecar.\n"
        f"  If backgrounded: a filter that outlives the command holds the task "
        f"open, so the completion notification may NEVER fire. Do not read "
        f"\"no notification yet\" as \"still running\" — check the status "
        f"document above.\n"
        f"`| tee out.txt` remains the filter that costs you nothing."
    )


# `pgrep` flags that consume the NEXT argv element. Without these the value
# would be mistaken for the pattern operand — `pgrep -f -u root foo` would
# report `root`, and the self-match test would then run against the wrong text.
_PGREP_VALUE_FLAGS = frozenset("dPuUgGstF")
_PGREP_LONG_VALUE_FLAGS = frozenset(
    (
        "--delimiter",
        "--parent",
        "--euid",
        "--uid",
        "--group",
        "--session",
        "--terminal",
        "--pgroup",
        "--pidfile",
        "--ns",
        "--nslist",
    )
)

# One `pgrep` invocation, up to the next command boundary. `|` is a boundary so
# a `| grep -v $$` filter is not swallowed into the flag scan.
_PGREP_CALL = re.compile(r"\bpgrep\b([^;|&\n()]*)")

# A wait loop, in the two halves that have to BOTH be present. The keyword
# alone matches `for f in *.rs` on one line of a longer command; the body alone
# matches a `do`/`done` belonging to something else.
_LOOP_KEYWORD = re.compile(r"\b(?:while|until|for)\b")
_LOOP_BODY = re.compile(r"\bdo\b.*\bdone\b", re.DOTALL)


def _pgrep_full_pattern(segment):
    """Return the pattern operand of a `pgrep` call that scans FULL argv.

    `None` when the call does not scan argv at all (no `-f`/`--full`), when it
    is anchored to the program name (`-x`/`--exact`, which cannot match a
    shell's long command line and is therefore already one of the fixes), or
    when there is no pattern to read."""
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        return None
    full = False
    exact = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token[:1] in (">", "<") or (token[:1].isdigit() and ">" in token):
            index += 1
            continue
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            if name == "--full":
                full = True
            elif name == "--exact":
                exact = True
            elif name in _PGREP_LONG_VALUE_FLAGS and "=" not in token:
                index += 1
            index += 1
            continue
        if token.startswith("-") and len(token) > 1:
            letters = token[1:]
            if "f" in letters:
                full = True
            if "x" in letters:
                exact = True
            if letters[-1] in _PGREP_VALUE_FLAGS:
                index += 1
            index += 1
            continue
        break
    if not full or exact or index >= len(tokens):
        return None
    return tokens[index]


def self_matching_pgrep_loop(command):
    """Return the pattern of a wait loop whose `pgrep -f` will match itself.

    `pgrep -f` scans every process's FULL command line, and the polling loop is
    itself a process whose command line contains the pattern — because the
    pattern is written inside it. So the loop finds itself, the condition never
    goes false, and it never exits. Observed 2026-08-25: a session sat in
    `until ! pgrep -f 'codeyam-editor editor commit'; do sleep 20; done`
    waiting on a commit that had already finished, because the only process
    still matching was the waiter.

    Three conditions, and each one earns its place:

    - A LOOP. A one-shot `pgrep -f` self-matches too, but it returns a wrong
      answer once; a loop never terminates. Only the second is worth a notice.
    - `-f` WITHOUT `-x`. `-x` matches the program name, which a shell's long
      command line can never equal — that is one of the fixes, not the hazard.
    - THE PATTERN ACTUALLY MATCHES THE COMMAND TEXT. This is what makes the
      rule discriminating rather than a blanket ban on `pgrep -f` in a loop: it
      lets the classic bracket trick through. `pgrep -f '[c]odeyam-editor'`
      contains no literal `codeyam-editor` run for its own regex to find, so it
      does not self-match, and it is correctly not flagged.

    A command that already excludes its own pid (`$$`) is likewise left alone —
    the author has seen this problem and handled it."""
    if not command or "pgrep" not in command:
        return None
    if not _LOOP_KEYWORD.search(command) or not _LOOP_BODY.search(command):
        return None
    if "$$" in command:
        return None
    for match in _PGREP_CALL.finditer(command):
        pattern = _pgrep_full_pattern(match.group(1))
        if not pattern:
            continue
        try:
            if re.search(pattern, command):
                return pattern
        except re.error:
            # Not a valid regex to Python. `pgrep` would reject it too, but the
            # substring test still answers the question that matters.
            if pattern in command:
                return pattern
    return None


def self_matching_pgrep_notice(pattern):
    """The advisory text for a self-matching wait loop — allowed, not refused.

    A notice rather than a block because nothing is destroyed and nothing needs
    recovering: the command is safe, it simply will not finish. It has to
    arrive BEFORE the command runs, because afterwards the agent is inside a
    loop that never returns and has no turn left in which to read anything.

    `wait-for` leads because it is this repo's sanctioned answer — it blocks to
    completion in one call and its exit code is trustworthy. The two `pgrep`
    repairs follow for the case where polling is genuinely what you want."""
    return (
        f"NOTE: this loop polls with `pgrep -f {pattern!r}`, and `pgrep -f` "
        f"matches against each process's FULL command line — including this "
        f"loop's own. The pattern is written inside the loop, so `pgrep` finds "
        f"the loop itself, the condition never goes false, and it never "
        f"exits.\n"
        f"  Best:  do not poll at all. `{cli_command()} editor wait-for "
        f"<task-id>` blocks to completion in ONE call and returns the real "
        f"verdict — or just keep working and let the harness completion "
        f"notification re-invoke you.\n"
        f"  Or:    match the program NAME instead of the argv: `pgrep -x "
        f"<name>`.\n"
        f"  Or:    exclude yourself: `pgrep -f {pattern!r} | grep -v $$`.\n"
        f"Observed 2026-08-25: a session waited on a commit that had already "
        f"finished, because the only process still matching was the waiter."
    )


def write_targets(command):
    """Parse `command` for in-process file-write constructs.

    Returns `(explicit, opaque, append_only)`: `explicit` lists the literal
    paths the command writes to; `opaque` is True when at least one write
    construct targets a path that cannot be resolved statically — a variable
    (`open(p, "w")`), or an in-place `sed`/`perl` whose file argument is
    positional.

    `append_only` is True when every construct found EXTENDS its target
    (`>>`, `open(p, "a")`) rather than replacing it. Appending is still a
    write and is still refused, but the refusal owes an accurate account of
    what the command did, so the distinction has to survive the parse instead
    of being discarded here. Mixed commands report False — of "this appends"
    and "this rewrites", the stronger claim is the true one."""
    explicit = []
    opaque = False
    appending = False
    truncating = False

    for match in _OPEN_CALL.finditer(command):
        args = _call_args(command, match.end() - 1)
        if len(args) < 2:
            continue
        mode = _string_literal(args[1])
        if mode is None or not set(mode) & set("wax+"):
            continue
        if "a" in mode:
            appending = True
        else:
            truncating = True
        literal = _string_literal(args[0])
        if literal:
            explicit.append(literal)
        else:
            opaque = True

    for pattern in (_WRITE_TEXT, _NODE_WRITE):
        for match in pattern.finditer(command):
            truncating = True
            if match.group("path"):
                explicit.append(match.group("path"))
            else:
                opaque = True

    for match in _SHELL_REDIRECT.finditer(command):
        if match.group(0).startswith(">>"):
            appending = True
        else:
            truncating = True
        explicit.append(match.group("path"))

    if _has_inplace_editor(command):
        opaque = True
        truncating = True

    return explicit, opaque, appending and not truncating


def _repo_relative(path, project_dir):
    """`path` expressed relative to `project_dir`, or None when it escapes the
    repo (an absolute path elsewhere, `~`, or a `../` climb)."""
    if not path or path.startswith("~"):
        return None
    if os.path.isabs(path):
        try:
            rel = os.path.relpath(path, project_dir)
        except ValueError:
            return None
    else:
        rel = path
    while rel.startswith("./"):
        rel = rel[2:]
    if not rel or rel.startswith(".."):
        return None
    return rel


def eligible_pathspecs(paths, project_dir):
    """The repo-relative, source-suffixed, pathspec-safe subset of `paths`,
    de-duplicated and capped at `_MAX_PATH_CANDIDATES`.

    Pure — no git, no filesystem. Split from `tracked_source_paths` so the
    normalize-and-filter half is testable without a git repository."""
    candidates = []
    for path in paths:
        rel = _repo_relative(path, project_dir)
        if not rel or not rel.lower().endswith(SOURCE_SUFFIXES):
            continue
        if not _PATHSPEC_SAFE.match(rel) or rel in candidates:
            continue
        candidates.append(rel)
        if len(candidates) >= _MAX_PATH_CANDIDATES:
            break
    return candidates


def tracked_source_paths(paths, project_dir):
    """The subset of `paths` that git tracks and that carries a source suffix.

    Untracked files, temp/scratchpad paths, and generated artifacts all fall
    out here — they are not tracked, so they are never blocked."""
    candidates = eligible_pathspecs(paths, project_dir)
    if not candidates:
        return []
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--"] + candidates,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return sorted(p for p in result.stdout.split("\0") if p)


def _path_tokens(command):
    """Every path-shaped substring in `command` that could name a file.
    Suffix and tracked-ness filtering happen in `tracked_source_paths`."""
    return [m.group(0) for m in _PATHLIKE.finditer(command)]


def _offending_stage(stages):
    """The first of `stages` that itself carries a write construct, or `""`
    when none can be attributed.

    Best-effort by design, and it must stay that way. `_split_commands` splits
    on `(`/`)` among others, so an INTERPRETER heredoc — the shape the whole
    guard was built from — shreds into stages like `open`, `p, "w"`, `.write`,
    none of which carries a recognisable write on its own. That is fine here
    (an unattributable stage simply suppresses the compound sentence) and would
    be catastrophic in the detection itself, which is why detection stays
    whole-command."""
    for stage in stages:
        explicit, opaque, _ = write_targets(stage)
        if explicit or opaque:
            return stage.strip()
    return ""


def scripted_rewrite_stage(command, project_dir):
    """`(tracked_path, stage, stage_count, append_only)` when `command` writes
    tracked source off-transcript, else None. `stage` is `""` when the
    offending half cannot be attributed; `append_only` is `write_targets`'
    construct verdict, carried through so the refusal can describe an append
    as an append.

    Detection is WHOLE-COMMAND, unchanged: a command qualifies only when it
    BOTH carries a write construct AND that write lands on tracked source.
    When every write target is a literal path, only those paths are judged.
    When a target is opaque, it falls back to every tracked source path the
    command mentions — which is the shape the real incidents took
    (`p = "…/opencode.rs"` … `open(p, "w")`, with the assignment and the write
    on different lines). Narrowing that fallback to a single stage silently
    disarms the guard on exactly those cases.

    Stage ATTRIBUTION is layered on top so the refusal can name the offending
    half of a compound command. One session ran `cp <file> <backup> && perl
    -0pi …`; the whole call was refused, so the backup never happened and the
    agent lost its safety net without being told — the splitter knew both
    stages and the refusal named only a file."""
    explicit, opaque, append_only = write_targets(command)
    if not explicit and not opaque:
        return None
    candidates = _path_tokens(command) if opaque else explicit
    tracked = tracked_source_paths(candidates, project_dir)
    if not tracked:
        return None
    stages = _split_commands(command)
    return (tracked[0], _offending_stage(stages), len(stages), append_only)


def scripted_source_rewrite_target(command, project_dir):
    """The git-tracked source file a scripted in-process rewrite would clobber,
    or None when `command` is not one. The verdict half of
    `scripted_rewrite_stage`, for callers that need only the path."""
    found = scripted_rewrite_stage(command, project_dir)
    return found[0] if found else None


# ── line-budget guard ──────────────────────────────────────────────────
#
# A codeyam-editor project caps `.claude/skills/codeyam-editor/SKILL.md` at a
# line count enforced by a Rust test (`skill_md_is_lean`). Nothing used to say
# so until that test went red — long after the content was written, and under
# Fast Commit possibly not until finalize. One session appended three bullets to
# a file already sitting at exactly 100 lines, discovered the wall from a red
# full-suite run, reverted its own work, and re-authored it as a step-library
# fragment. The content ended up in the right place; the detour was pure waste.
#
# These helpers mirror `commands::editor::line_budget`'s parsing so an edit that
# would exceed the budget is refused BEFORE it lands. They mirror the *parsing*,
# never the *number* — the cap is read from the test that declares it, so raising
# or lowering it stays a one-line edit there.

# Directories never worth walking for the contract test. Mirrors
# `control-api`'s `ALWAYS_EXCLUDED_DIRS`.
_BUDGET_SCAN_EXCLUDED_DIRS = frozenset(("node_modules", ".codeyam", ".git", "target"))

# Upper bound on Rust files examined while looking for the contract. The real
# marker sits in a test file near the top of the walk; the cap only stops a
# pathological tree from making a PreToolUse hook slow.
_BUDGET_SCAN_MAX_FILES = 4000

# The "approaching the cap" gradient lives in `line_budget::WARN_MARGIN` and is
# reported by `classify-constrained-files` at plan time. It is deliberately NOT
# mirrored here: this hook can only speak by refusing (exit 2), and a refusal is
# the wrong response to an edit that still fits. What this guard owes is the
# hard stop, worded so the author never has to discover the wall by test.


def _is_rust_comment(line):
    """True for a Rust comment line. Comments DISCUSS the contract; they never
    declare it. Load-bearing: `line_budget.rs`'s own doc comment names the parsed
    construct, and a parser that read comments latched onto that placeholder and
    reported a guarded path of `…SKILL.md` — a lookup matching no real file, which
    silently disabled this guard."""
    return line.lstrip().startswith("//")


def read_rel_skill_path(line):
    """The guarded SKILL.md argument of a `read_rel("…")` call, or None."""
    if _is_rust_comment(line):
        return None
    parts = line.split('read_rel("')
    if len(parts) < 2:
        return None
    literal = parts[1].split('"')[0]
    return literal if literal.endswith("SKILL.md") else None


def line_count_limit(line):
    """The integer N from a `line_count <= N` assertion on `line`, or None."""
    if _is_rust_comment(line):
        return None
    parts = line.split("line_count <=")
    if len(parts) < 2:
        return None
    digits = ""
    for ch in parts[1].lstrip():
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else None


def parse_lean_contract(test_src):
    """`(guarded repo-relative path, max line count)` from the contract test
    source, or None when either literal is absent."""
    path = None
    limit = None
    for line in test_src.splitlines():
        if path is None:
            path = read_rel_skill_path(line)
        if limit is None:
            limit = line_count_limit(line)
        if path is not None and limit is not None:
            return (path, limit)
    return None


def _is_integration_test_path(path):
    """True when `path` sits under a `tests/` directory.

    The enforced contract is an integration test. A `src/` file carrying the
    marker is documentation about the contract or a test *fixture* imitating it —
    `line_budget.rs` and `classify_constrained_files.rs` both hold one — and
    parsing a fixture yields a cap that belongs to nobody."""
    return "tests" in path.replace("\\", "/").split("/")


def discover_lean_contract(project_dir):
    """Scan the project's Rust integration tests for the `skill_md_is_lean`
    marker and parse the contract out of it. None when the project enforces no
    cap — the correct degradation, and what makes this guard silent on every
    project that is not codeyam-editor itself."""
    examined = 0
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in _BUDGET_SCAN_EXCLUDED_DIRS]
        if not _is_integration_test_path(os.path.relpath(root, project_dir)):
            continue
        for name in files:
            if not name.endswith(".rs"):
                continue
            examined += 1
            if examined > _BUDGET_SCAN_MAX_FILES:
                return None
            try:
                with open(os.path.join(root, name), "r", encoding="utf-8") as f:
                    src = f.read()
            except Exception:
                continue
            if "skill_md_is_lean" in src:
                parsed = parse_lean_contract(src)
                if parsed:
                    return parsed
    return None


def projected_line_count(tool_name, tool_input, current_body):
    """The line count `file_path` would have AFTER this Write/Edit, or None when
    it cannot be determined.

    Write replaces the whole file, so its `content` is the answer outright. Edit
    is computed by performing the same substring replacement in memory — exact,
    rather than a line-delta estimate that drifts on a multi-line old_string. An
    Edit whose `old_string` is not present changes nothing, so it is left to the
    Edit tool's own error rather than judged here."""
    if tool_name == "Write":
        content = tool_input.get("content")
        return None if content is None else len(content.splitlines())
    old = tool_input.get("old_string")
    new = tool_input.get("new_string")
    if current_body is None or old is None or new is None or old not in current_body:
        return None
    if tool_input.get("replace_all"):
        return len(current_body.replace(old, new).splitlines())
    return len(current_body.replace(old, new, 1).splitlines())


def line_budget_refusal(rel_path, limit, current, projected):
    """The `(reason, next_action)` pair for an edit that would break a file's
    line budget.

    The reason states the arithmetic — an author who sees `100/100, this edit
    makes it 103` knows immediately that the target is wrong rather than that the
    file is off limits. The next action names the whole fragment mechanism: the
    command, the file it writes, the placeholder, the substitution site, and the
    leak test. Naming only the destination ("move it into step .txt files") is
    what left the four steps to be rediscovered by reading a sibling."""
    return (
        f"`{rel_path}` is at its enforced line budget: {current}/{limit} lines, and "
        f"this edit would make it {projected}. The `skill_md_is_lean` test would go "
        f"red — possibly not until finalize, long after this content is written. The "
        f"cap is not a bug to route around: hitting it is what moves operational "
        f"guidance into the step library, where a step body re-reads it every step "
        f"instead of once per session.",
        f"author a step-library fragment instead. Run "
        f"`{cli_command()} editor new-step-fragment <name> --slug <slug>`: it writes "
        f"crates/codeyam-editor/src/commands/editor/steps/library/fragments/<name>_block.txt, "
        f"adds the `include_str!` substitution for `{{<name>_block}}` in "
        f"crates/codeyam-editor/src/commands/editor/step.rs, inserts the placeholder into "
        f"each named slug's .txt, and prints the placeholder-leak test to add. Then put "
        f"this guidance in that fragment. To check any file's remaining headroom first: "
        f"`{cli_command()} editor classify-constrained-files {rel_path}`.",
    )


def line_budget_violation(tool_name, tool_input, project_dir):
    """`(rel_path, limit, current, projected)` when this Write/Edit would push a
    line-budgeted file past its cap, else None.

    Cheap in the common case: the contract scan is skipped entirely unless the
    target is named `SKILL.md`, so an ordinary source edit pays one basename
    comparison."""
    file_path = tool_input.get("file_path", "")
    if os.path.basename(file_path) != "SKILL.md":
        return None
    rel = _repo_relative(file_path, project_dir)
    if not rel:
        return None
    contract = discover_lean_contract(project_dir)
    if not contract:
        return None
    guarded, limit = contract
    if rel.replace("\\", "/") != guarded:
        return None
    try:
        with open(os.path.join(project_dir, guarded), "r", encoding="utf-8") as f:
            body = f.read()
    except Exception:
        body = None
    projected = projected_line_count(tool_name, tool_input, body)
    if projected is None or projected <= limit:
        return None
    current = len(body.splitlines()) if body is not None else 0
    return (rel, limit, current, projected)


def compound_stage_evidence(stage, stage_count):
    """The sentence a refused COMPOUND command owes: which stage matched, and
    that nothing ran.

    A refusal is all-or-nothing — the hook returns exit 2 before the shell sees
    any of it — so the safe half of `cp <backup> && perl -0pi …` is lost too.
    Saying which half matched, and that the other did NOT run, is the difference
    between re-issuing the safe half and silently continuing without it.

    Silent when the stage cannot be attributed. An interpreter heredoc splits
    into many pseudo-stages that are fragments of one program, not commands, so
    claiming it is an "11-stage compound command" would be worse than saying
    nothing."""
    if not stage or stage_count < 2:
        return ""
    return (
        f"this is a {stage_count}-stage compound command and the match is in "
        f"stage `{stage}`; NOTHING ran — the other stage(s) were refused with "
        f"it, so re-issue any safe half (a `cp` backup, a `mkdir`) on its own"
    )


def scripted_rewrite_refusal(path, append_only=False):
    """The `(reason, next_action)` pair for a refused scripted write. Names the
    path that matched and the sanctioned alternatives — batching is the reason
    agents reach for a script, so the refusal has to answer it.

    Branches on the CONSTRUCT, not the file. `cat >> file` is refused for the
    same two reasons a rewrite is (the diff is computed at runtime so it never
    reaches the transcript, and it bypasses Edit's file-state tracking), but it
    does not parse the file or self-match generated code, and none of
    `replace_all` / `rename-symbol` answers "add 100 lines to the end". Calling
    it a rewrite and offering replace-shaped recoveries left the agent to
    re-read the file tail and synthesize an anchor by hand — the round trip
    that made this the most-hit block on the fleet."""
    if append_only:
        return (
            f"this command appends to the tracked source file `{path}`. "
            f"An append is still a write whose diff is computed at runtime, so "
            f"the change never appears in the transcript a reviewer reads; and "
            f"it bypasses the file-state tracking that lets Edit refuse a file "
            f"that changed underneath it.",
            f"use the Edit tool anchored on the file's existing final construct: "
            f"`old_string` is that construct verbatim, `new_string` is that same "
            f"construct followed by the new content. Batching is not a reason to "
            f"script — several Edit calls in ONE message run in parallel. Writing "
            f"to an untracked file, to /tmp, or to the scratchpad is unaffected.",
        )
    return (
        f"this command machine-rewrites the tracked source file `{path}`. "
        f"A scripted in-process rewrite (`open(p, 'w')`, `.write_text(`, `sed -i`, "
        f"`perl -pi`) computes its diff at runtime, so the change never appears in "
        f"the transcript a reviewer reads; it parses the language with the wrong "
        f"grammar and self-matches the code it just generated; and it bypasses the "
        f"file-state tracking that lets Edit refuse a file that changed underneath "
        f"it.",
        f"use the Edit tool. Batching is not a reason to script — "
        f"several Edit calls in ONE message run in parallel. For a genuine "
        f"replace-every-occurrence pass use Edit with `replace_all: true`; to rename "
        f"an identifier across source + glossary + registry run "
        f"`{cli_command()} editor rename-symbol`. Writing to an untracked file, to "
        f"/tmp, or to the scratchpad is unaffected.",
    )


# --- Recursive-delete guard ------------------------------------------------
#
# A recursive delete is the most destructive thing an agent can do to a working
# tree and the one whose damage is invisible until something else surfaces it.
# `rm -rf crates/codeyam-editor/.codeyam` was issued in the belief that it was
# stray generated output; it was 12 git-TRACKED fixture files, and nothing said
# so until a later `git status`.
#
# The mistake was reasonable. `.codeyam/` at the repo root IS internal cache
# state (it is in `ALWAYS_EXCLUDED_DIRS`), and the same directory name one level
# down inside a crate is a tracked test fixture. That ambiguity is not going
# away — which is exactly why the guard keys on git-tracked-ness rather than on
# a denylist of directories that "look like cache". A denylist is the reasoning
# that caused the loss. Whether git tracks a file is the fact that actually
# matters, it is cheap to ask, and it generalizes to every fixture directory in
# every client project.
#
# There is deliberately no bypass flag. A rule an agent can wave away under time
# pressure is not a guard, and a genuinely intended deletion of tracked files
# already has a reversible, reviewable spelling: `git rm`.
#
# Scope is recursive deletes only. A single `rm <file>` names exactly what it
# removes and is visible in the transcript; `-r` against a directory is the
# shape whose blast radius the author cannot see.

_RM_LONG_RECURSIVE = "--recursive"

# The shortest unambiguous abbreviation GNU `rm` accepts for `--recursive`.
# `--recursive` is the only long option of `rm` beginning with `r`, so getopt
# resolves `--r` to it.
_RM_LONG_RECURSIVE_MIN = len("--r")

# Textual last resort when a segment cannot be tokenized. Matches `rm` only in
# command position (start of segment, or after a separator) so a mention inside
# an unterminated string is not one.
_RM_TEXTUAL = re.compile(r"(?:^|[\s;|&(])(?:[^\s;|&]*/)?rm(?=\s)")
_RM_TEXTUAL_RECURSIVE = re.compile(r"(?:^|\s)-(?:-r|[A-Za-z]*[rR])")


def is_recursive_rm_flag(token):
    """True when `token` is `rm`'s recursive flag in any spelling it accepts:
    `-r`, `-R`, a short cluster containing either (`-rf`, `-fr`, `-Rf`), or
    `--recursive` and its unambiguous abbreviations.

    Clustering needs no value-flag stop list the way grep's `-P` does: none of
    `rm`'s short options takes a value, so every letter in a cluster is a flag
    and `r` anywhere in one means recursive."""
    if token.startswith("--"):
        return (
            len(token) >= _RM_LONG_RECURSIVE_MIN
            and _RM_LONG_RECURSIVE.startswith(token)
        )
    if not token.startswith("-") or token == "-":
        return False
    return any(ch in "rR" for ch in token[1:])


def recursive_rm_operands(tokens):
    """The paths a recursive `rm` in one already-split command would delete, or
    `[]` when this command is not a recursive `rm`.

    `_in_command_position` is what keeps `grep -rn "rm -rf" .claude/` and
    `git commit -m "drop rm -rf from the script"` from reading as deletions —
    in both, `rm` is an argument, and in the second it is not even a token of
    its own. Everything after a `--` terminator is an operand, including a path
    that begins with a dash."""
    for index, tok in enumerate(tokens):
        if _program_name(tok) != "rm":
            continue
        if not _in_command_position(tokens, index):
            continue
        recursive = False
        operands = []
        end_of_flags = False
        for arg in tokens[index + 1:]:
            if end_of_flags:
                operands.append(arg)
            elif arg == "--":
                end_of_flags = True
            elif arg.startswith("-") and arg != "-":
                recursive = recursive or is_recursive_rm_flag(arg)
            else:
                operands.append(arg)
        if recursive and operands:
            return operands
    return []


def tracked_file_count(path, project_dir):
    """How many git-tracked files live AT or UNDER `path`.

    Deliberately not `tracked_source_paths`: that filters to source suffixes,
    and the files actually lost here were `.json` fixtures. A delete does not
    care what a reviewer reads as a diff — every tracked file it removes counts.

    Asked as TWO pathspecs, which is not redundancy. Git's directory-prefix
    rule — the thing that makes the bare path `fixtures/.codeyam` match every
    file beneath it — applies only to a LITERAL pathspec. The moment the
    operand carries a glob the pattern is fnmatched instead, and
    `crates/*/.codeyam` matches no file at all, because the real entries carry
    a `/editor.json` tail the pattern does not cover. That is exactly the shape
    that would wipe the fixture out of every crate at once, so it cannot be the
    one shape that slips through. Appending `/*` gives the glob case a pattern
    that does match, and costs the literal case nothing (`ls-files` reports
    each index entry once however many pathspecs select it).

    Returns 0 when the path escapes the repo, is not pathspec-safe, or git
    cannot answer. Those are all "this guard has nothing to say", not "this is
    safe": a path outside the repo is not git's to protect, and a guard that
    blocked on an unanswerable question would refuse ordinary `rm -rf /tmp/…`
    and `rm -rf node_modules` on every project where git happens to be
    unavailable.

    Two shapes are statically undecidable and therefore NOT covered, by
    construction rather than by oversight: an unexpanded variable
    (`rm -rf "$BUILD_DIR"`) and a `find … -exec rm -rf {} +` placeholder. In
    both the operand names no path until the shell or `find` produces one, and
    refusing on unknowability would refuse the legitimate majority of both
    shapes. This is the same best-effort boundary `_has_inplace_editor` and
    `_uses_pcre_grep` draw."""
    rel = _repo_relative(path, project_dir)
    if rel is None or not _PATHSPEC_SAFE.match(rel):
        return 0
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", rel, f"{rel.rstrip('/')}/*"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return 0
    if result.returncode != 0:
        return 0
    return len([p for p in result.stdout.split("\0") if p])


def tracked_recursive_rm(command, project_dir):
    """`(path, tracked_count)` for the first recursive-`rm` target in `command`
    that git tracks, else None. `tracked_count` is None when the segment could
    not be tokenized.

    Scoped per split command, so a delete buried in an `&&` chain is seen on its
    own, and re-entered for a `bash -c` payload — the two shapes that would
    otherwise hide the operand inside a single opaque token.

    Fails closed on a malformed quote, but only for a segment that textually
    looks like a recursive `rm`. The blanket fail-closed its sibling predicates
    use (`_has_inplace_editor` returns True for any untokenizable command) would
    refuse every mistyped quote in every session; narrowing it to the shape this
    guard is about keeps the evasion path shut without that cost."""
    for segment in _split_commands(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            if _RM_TEXTUAL.search(segment) and _RM_TEXTUAL_RECURSIVE.search(segment):
                return (segment.strip(), None)
            continue
        for operand in recursive_rm_operands(tokens):
            count = tracked_file_count(operand, project_dir)
            if count:
                return (operand, count)
        payload = _shell_c_payload(tokens)
        if payload is not None:
            nested = tracked_recursive_rm(payload, project_dir)
            if nested:
                return nested
    return None


def recursive_rm_refusal(path, tracked_count):
    """The `(reason, next_action)` pair for a refused recursive delete.

    Names the path, the count, and `git rm -r` — the count is what turns "this
    looked like build output" into a fact the author can check, and `git rm` is
    the same deletion in a form that is staged, reviewable, and undoable."""
    if tracked_count is None:
        return (
            f"this command could not be parsed, and it looks like a recursive "
            f"`rm`: `{path}`. The hook cannot tell whether it would delete "
            f"git-tracked files, and a recursive delete is not recoverable from "
            f"the transcript.",
            "fix the quoting and re-run, so the target can be checked against "
            "git. If the delete is genuinely aimed at tracked files, run "
            "`git rm -r <path>` instead.",
        )
    return (
        f"this command recursively deletes `{path}`, which holds "
        f"{tracked_count} git-tracked file(s). Tracked files are not build "
        f"output — a directory that looks like cache can be a committed test "
        f"fixture (`crates/*/.codeyam/` is exactly that, while `.codeyam/` at "
        f"the repo root is real internal state). Nothing surfaces the loss "
        f"until a later `git status`.",
        f"if you mean to delete it, run `git rm -r {path}` — the same removal, "
        f"staged and reversible (`git restore --staged {path}` then "
        f"`git checkout -- {path}`) and visible in review. If you meant to clear "
        f"generated output, name the untracked path directly; untracked paths "
        f"(`target/`, `node_modules/`, scratch dirs) are not guarded.",
    )


def read_event():
    """The PreToolUse event from stdin, or None when it is absent or
    unparseable — in which case the hook allows rather than blocks."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        return json.loads(raw)
    except Exception:
        return None


# Internal `.codeyam/` state stores that have a purpose-built inspector,
# mapped to the command that answers questions about them. Ordered
# most-specific-path first so `.codeyam/test-cache/blobs/…` matches the
# cache inspector rather than a broader prefix.
#
# These are stores whose on-disk shape is INTERNAL and undocumented at the
# read site: a hand-rolled walk has to guess whether a field is a string
# or a list, and the observed failures were exactly that guess going wrong
# (`'list' object has no attribute 'split'`, `JSONDecodeError` on a
# blob file that had been externalized). The inspectors interpret the
# store instead, so the question is answerable without knowing the schema.
_INSPECTOR_BY_STORE = [
    (".codeyam/logs/audit-history.jsonl", "audit-history"),
    (".codeyam/state/finalize-debt.json", "finalize-debt"),
    (".codeyam/dependency-graph.json", "deps-imports / deps-imported-by"),
    (".codeyam/test-registry.json", "registry-query"),
    (".codeyam/per-test-evidence.json", "evidence-query"),
    (".codeyam/project-deliverables.json", "deliverables"),
    (".codeyam/editor.local.json", "config-show --source"),
    (".codeyam/scenarios/coverage-plan", "scenario-coverage-plan"),
    (".codeyam/scenarios/_shared", "shared-data"),
    (".codeyam/editor-step.json", "step"),
    (".codeyam/glossary.json", "glossary-find / glossary-list"),
    (".codeyam/editor.json", "config-query (testRunners / staticChecks) / config-show"),
    (".codeyam/stack.json", "project-info"),
    (".codeyam/scenarios", "scenarios / scenario-explain"),
    (".codeyam/test-cache", "test-cache-query"),
    (".codeyam/journal", "journal-find"),
    (".codeyam/plans", "plans / plan-show"),
]

# A path under `.codeyam/` naming something more specific than the
# directory itself. Used only for the no-inspector case, so `ls .codeyam/`
# — an ordinary first look around — stays quiet while a probe of a
# particular state file is answered.
_CODEYAM_STATE_PATH = re.compile(r"\.codeyam/[A-Za-z0-9_.][A-Za-z0-9_./+-]*")

# Read-shaped commands, matched in COMMAND POSITION — at the start of the
# string or just after a shell separator, allowing leading `VAR=value`
# assignments and transparent prefixes. Position is what distinguishes a
# probe from an incidental mention: `git ls-files .codeyam/glossary.json`
# and `git add .codeyam/test-registry.json` both name a store without
# reading it the way this nudge is about, and neither matches here.
#
# The verb set is the python forms the nudge has always covered plus the
# shell reads agents actually reach for. The rationale in
# `inspector_nudge`'s docstring was never python-specific: `ls` on a
# guessed path re-derives a store's layout exactly the way a python walk
# re-derives its schema, and fails the same way.
_READ_VERB = re.compile(
    r"""(?:\A|[\n;|&`(]|\$\()\s*
        (?:[A-Za-z_][A-Za-z_0-9]*=\S*\s+)*
        (?:(?:sudo|command|time|xargs)\s+)*
        (?:python3?|ls|cat|head|tail|wc|jq|grep|find)\b
    """,
    re.VERBOSE,
)

# A `codeyam-editor editor …` invocation, under either the canonical name
# or the local-dev branding.
_INSPECTOR_INVOCATION = re.compile(r"\bcodeyam-editor(?:-dev)?\s+editor\b")


def is_read_shaped_command(command):
    """True when `command` READS something in command position — a python
    invocation or a shell read verb.

    Pure and side-effect free so the predicate can be tested directly,
    separately from the store mapping it gates."""
    return bool(_READ_VERB.search(command))


def is_inspector_invocation(command):
    """True when `command` runs a `codeyam-editor editor …` subcommand.

    An inspector necessarily names the store it inspects, so nudging one
    would point the agent at the command it is already running."""
    if _INSPECTOR_INVOCATION.search(command):
        return True
    return f"{cli_command()} editor " in command


def matching_inspector(command):
    """The `(store, inspector)` pair `command` touches, or None.

    Separated from the message that reports it so the
    longest-path-first ordering of `_INSPECTOR_BY_STORE` — which is what
    keeps `.codeyam/scenarios/_shared/…` from resolving to the broader
    scenarios entry — is assertable without going through message text."""
    for store, inspector in _INSPECTOR_BY_STORE:
        if store in command:
            return (store, inspector)
    return None


def probed_state_path(command):
    """The `.codeyam/` state path `command` names, or None.

    A bare `.codeyam/` is deliberately not a match: listing the
    directory is an ordinary first look around, not a probe of a
    particular store, and nudging it would be noise."""
    match = _CODEYAM_STATE_PATH.search(command)
    return match.group(0) if match else None


def inspector_nudge(command):
    """Return a pointer to the matching inspector when `command` reads a
    `.codeyam/` state store, else None. When the probed store has no
    inspector, say so rather than staying silent — the absence is a fact
    worth reporting, since silence reads as "no such command found".

    Pure and side-effect free so the mapping can be tested directly.

    This is a NUDGE, never a block. Reading internal state by hand is
    wasteful, not incorrect — the reader re-derives a shape that a
    command already knows, and gets it wrong often enough to cost a turn
    plus a re-read. That asymmetry is what makes a pointer the right
    instrument and a refusal the wrong one: a block would strand an agent
    whose question genuinely has no inspector. It matters more under the
    wider trigger, not less — a broader net means more false positives,
    which is an argument for keeping the instrument soft."""
    # Heredoc bodies are elided for the same reason the gates elide them: a
    # commit message that MENTIONS `.codeyam/glossary.json` is prose, and
    # nudging it would point at an inspector for a store nothing is reading.
    command = elide_heredoc_bodies(command)
    if is_inspector_invocation(command):
        return None
    if not is_read_shaped_command(command):
        return None
    matched = matching_inspector(command)
    if matched:
        store, inspector = matched
        return (
            f"NOTE: this reads {store} — an internal codeyam state store. "
            f"`{cli_command()} editor {inspector}` answers questions about it directly, "
            f"and interprets the store rather than dumping it, so the field shapes are "
            f"named instead of guessed. Not blocking; your command still runs."
        )
    probed = probed_state_path(command)
    if probed:
        return (
            f"NOTE: this reads {probed} — internal codeyam state with no "
            f"read-only inspector. No `{cli_command()} editor` verb interprets it, so "
            f"reading the file is the only option here; the absence is real, not "
            f"something you missed. Not blocking; your command still runs."
        )
    return None


# ── scripted state-read guard ──────────────────────────────────────────
#
# `inspector_nudge` above is the SOFT, editor-mode-only pointer: it fires on
# any read verb touching `.codeyam/` and it only ever advises. This guard is
# the narrow, always-on companion for the one shape that keeps recurring —
# a command that PARSES a `.codeyam/` store as JSON.
#
# The measurement that motivates it: across 12 autonomous sessions agents
# hand-parsed `.codeyam/` state with ad-hoc `json.load` heredocs 84 times in
# 10 of the 12, producing 12 `JSONDecodeError` crashes. `journal-commit-message`
# scored ZERO uses against 34 hand-rolls and 36 hardcoded timestamps — and it
# was already documented by name in the very CLAUDE.md table whose other
# commands enjoy healthy adoption. Prose has now failed twice on that one, so
# it gets the mechanical instrument instead.
#
# Two verdicts, and the split is deliberate:
#
#   NOTICE for a mapped store — reading state by hand is wasteful, not
#   incorrect, and a block would strand a legitimate one-off inspection.
#   Same asymmetry `inspector_nudge` reasons from.
#
#   BLOCK for the two cases where there is no reading under which the
#   result is TRUSTWORTHY. Parsing `state/command-output/*` is parsing a
#   live tee of two interleaved streams — not a document, and no
#   brace-matcher makes it one (one session wrote four successive
#   brace-balancing heredocs against it before giving up). Building a commit
#   body from a hand-named journal entry silently attributes another
#   feature's description, which is precisely what the command's own entry
#   resolution exists to prevent.
#
# It fires BEFORE the `CODEYAM_EDITOR_ACTIVE` short-circuit, unlike
# `inspector_nudge`: a commit body carrying the wrong feature's description
# is just as wrong outside the editor workflow as inside it.

# JSON-parsing constructs. Deliberately narrower than `_READ_VERB` — this
# guard has a blocking half, so it keys on the construct that makes the
# result untrustworthy rather than on reading in general.
_JSON_PARSE_CALL = re.compile(r"\b(?:json\.loads?|JSON\.parse)\s*\(")

# `jq` in COMMAND POSITION, mirroring `_READ_VERB`'s shape: a `jq` mentioned
# inside a filter string is not a parse of anything.
_JQ_INVOCATION = re.compile(
    r"""(?:\A|[\n;|&`(]|\$\()\s*
        (?:[A-Za-z_][A-Za-z_0-9]*=\S*\s+)*
        (?:(?:sudo|command|time|xargs)\s+)*
        jq\b
    """,
    re.VERBOSE,
)

# The transcript sidecar. Kept out of `_INSPECTOR_BY_STORE` on purpose: that
# table maps a store to the command that ANSWERS questions about it, and
# nothing answers questions about this file — the recovery is to re-run the
# original command differently, which is a refusal's job, not a pointer's.
_COMMAND_OUTPUT_STORE = ".codeyam/state/command-output"

# The scope is the FILE, not the directory, and that distinction is the whole
# point. The untrustworthiness is a property of one file shape — the `<cmd>.txt`
# tee of stdout AND stderr — never of the store that holds it. Its sibling
# `<cmd>.status.json` is a single clean JSON document, and reading it is the
# DOCUMENTED recovery after piping a command: `piped_gating_notice` hands the
# agent that exact path as `Real verdict: …`. A directory-prefix match therefore
# had this file refusing the read its own sibling guard prescribes — caught by
# dogfooding one command after the guard shipped, when `push` printed the
# sidecar path and reading it was blocked in the same session that added the
# block. Two guards in one file giving opposite instructions about one file.
#
# `<task>.heartbeat` is the same shape of read (a one-line liveness sidecar
# CLAUDE.md also directs agents to) and lives outside this directory, so it was
# never caught — but keying on the transcript rather than on a filename
# exception is what keeps it, and any future sidecar, correct by construction.
#
# Do NOT re-widen this to a `in command` membership test on the store.
_COMMAND_OUTPUT_TRANSCRIPT = re.compile(
    re.escape(_COMMAND_OUTPUT_STORE) + r"/[^/\s'\"]+\.txt\b"
)

# The HARNESS's own persisted tool-result transcript — the file Claude Code
# writes whenever a command's output exceeds the inline budget, and hands back
# as "Full output saved to: …/tool-results/<id>.txt". It is the same shape as
# the command-output tee above (both streams, bounded, written for a human),
# so it fails a scripted parse the same way, and agents reach for it for the
# same reason.
#
# Keyed on the `tool-results/<id>.txt` FILE, on the same terms and for the same
# reason as `_COMMAND_OUTPUT_TRANSCRIPT` above: match the file, never the
# directory it lives in. The lookbehind keeps `my-tool-results/x.txt` out.
#
# Deliberately NOT anchored on the `~/.claude/projects/` prefix, because that
# prefix is not stable: it is `/root/.claude/…` in a fleet container,
# `/Users/<name>/.claude/…` on a laptop, and anywhere at all under
# `CLAUDE_CONFIG_DIR`. The `tool-results/` segment is the part that does not
# move.
_HARNESS_TOOL_RESULT_TRANSCRIPT = re.compile(
    r"(?<![\w.-])tool-results/[^/\s'\"]+\.txt\b"
)

_HARNESS_TOOL_RESULTS_STORE = "tool-results"

# A journal entry named by a literal timestamp — the `<eyeballed-from-ls>`
# shape. A journal read that does NOT name one is an ordinary search and
# stays a notice pointing at `journal-find`.
#
# Kept out of `_INSPECTOR_BY_STORE` for the same reason `_COMMAND_OUTPUT_STORE`
# is, plus one specific to it: adding a `.codeyam/journal/entries` row ahead of
# `.codeyam/journal` would re-point `matching_inspector` — and therefore
# `inspector_nudge`, which is not what this change is about — at
# `journal-commit-message` for every journal read, including the searches
# `journal-find` genuinely answers. `test_matching_inspector_maps_the_journal_store`
# pins that mapping, and it is pinning the right thing.
_HAND_NAMED_JOURNAL_ENTRY = re.compile(r"\.codeyam/journal/entries/20\d\d-")

_JOURNAL_ENTRIES_STORE = ".codeyam/journal/entries"


def parses_json(command):
    """True when `command` parses JSON in process — a python/node parse call,
    or `jq` in command position.

    Pure and side-effect free so the construct test is assertable separately
    from the store mapping it gates."""
    return bool(_JSON_PARSE_CALL.search(command) or _JQ_INVOCATION.search(command))


def parses_command_output_transcript(command):
    """True when `command` names the command-output TRANSCRIPT — a
    `.codeyam/state/command-output/<cmd>.txt` path.

    Deliberately narrower than the store it lives in. The `.txt` tee is the
    unparseable file; the `<cmd>.status.json` sidecar beside it is a single
    clean JSON document that `piped_gating_notice` tells the agent to read.
    Both are named from the same `<cmd>` stem in the same directory, so the
    SUFFIX is the only thing that separates them — which is why the predicate
    keys on it and not on the directory prefix.

    Pure and side-effect free, and named rather than inlined into
    `scripted_state_read_target`, so the boundary between the two files is
    assertable directly instead of through a refusal's message text."""
    return bool(_COMMAND_OUTPUT_TRANSCRIPT.search(command))


def parses_harness_tool_result(command):
    """True when `command` names the harness's own tool-result TRANSCRIPT — a
    `…/tool-results/<id>.txt` path.

    The file-shaped counterpart to `parses_command_output_transcript`, and
    narrow for the same reason: it matches the `<id>.txt` capture itself, never
    the session directory holding it, so a future sibling written beside it is
    not swept in by a directory-prefix match — the boundary that had the
    command-output guard refusing the read of the `.status.json` its own other
    guard prescribes.

    Pure and side-effect free, and named rather than inlined into
    `scripted_state_read_target`, so the boundary is assertable directly
    instead of through a refusal's message text."""
    return bool(_HARNESS_TOOL_RESULT_TRANSCRIPT.search(command))


def writes_into_codeyam(command):
    """True when `command` WRITES to a `.codeyam/` path, or writes somewhere
    this parser cannot resolve.

    The exclusion that keeps the guard off the sanctioned path: CLAUDE.md
    explicitly blesses rewriting `.json` through a parser, and a heredoc that
    builds a scenario file reads its neighbours to do so. Judging such a
    command on its `json.load` alone would refuse the very construct the
    project asks for.

    Scoped to `.codeyam/` targets rather than to writes in general, so an
    ordinary `… > out.json` capture of a hand-parse is still seen. An opaque
    target counts, because a write this parser could not resolve may well be
    the scenario write."""
    explicit, opaque, _ = write_targets(command)
    if opaque:
        return True
    return any(".codeyam/" in path for path in explicit)


def scripted_state_read_target(command):
    """The `(kind, store, inspector)` a scripted JSON parse of codeyam state
    touches, or None when `command` is not one.

    `kind` is `"command-output"`, `"harness-tool-result"` or `"journal-entry"`
    for the three blocking cases, `"inspectable"` for a mapped store that only
    warrants a pointer. `inspector` is None for every blocking kind: each
    carries its recovery in `scripted_state_read_refusal` rather than in the
    shared store table, so none of them perturbs what `matching_inspector`
    reports.

    All three blocking cases are tested BEFORE the table lookup AND before the
    write exclusion. Order is the whole mechanism, twice over.

    Before the table, because a hand-named journal entry also matches the
    broader `.codeyam/journal` row, and letting the table win would downgrade
    a misattributed commit body to a pointer.

    Before the write exclusion, because the canonical failure WRITES: it reads
    a journal entry and writes the commit body out. When that output path is a
    variable rather than a literal, `write_targets` reports it opaque, and an
    exclusion applied first would suppress the block on precisely the shape
    the guard exists for. The exclusion protects the sanctioned scenario
    write, which is a `.codeyam/scenarios/` write — never a parse of the
    command-output tee, never a regex carved out of the harness's own capture
    of one, and never a commit body built from an eyeballed timestamp. No
    blocking case has a reading under which the result is trustworthy,
    whatever else the command does with it.

    Pure and side-effect free — the verdict is separated from the message
    that reports it so the mapping is assertable without going through
    message text, exactly as `matching_inspector` is.

    Heredoc bodies are elided on the same terms every other guard elides
    them: `elide_heredoc_bodies` keeps an EXECUTING body (`python3 - <<'EOF'`
    is a program) and drops a DATA one, so a commit message that quotes a
    `json.load(...)` line as prose — this feature's own plan file does — is
    not read as a parse of anything."""
    command = elide_heredoc_bodies(command)
    if is_inspector_invocation(command):
        return None
    if not parses_json(command):
        return None
    if parses_command_output_transcript(command):
        return ("command-output", _COMMAND_OUTPUT_STORE, None)
    if parses_harness_tool_result(command):
        return ("harness-tool-result", _HARNESS_TOOL_RESULTS_STORE, None)
    if _HAND_NAMED_JOURNAL_ENTRY.search(command):
        return ("journal-entry", _JOURNAL_ENTRIES_STORE, None)
    if writes_into_codeyam(command):
        return None
    matched = matching_inspector(command)
    if not matched:
        return None
    store, inspector = matched
    return ("inspectable", store, inspector)


def scripted_state_read_refusal(kind):
    """The `(reason, next_action)` pair for a refused scripted state read.

    Branches on the KIND, not the store, because the three blocking cases fail
    for unrelated reasons and want unrelated recoveries — one re-runs the
    original command with a different flag, one points at a document already on
    disk, and one swaps to a command that resolves the entry itself."""
    if kind == "command-output":
        return (
            f"this parses `{_COMMAND_OUTPUT_STORE}/<cmd>.txt`, which is a live "
            f"TEE of stdout AND stderr in arrival order. The JSON document sits "
            f"interleaved with narrative lines, so the file is not a JSON "
            f"document and no brace-matcher or regex rescue can make it one — "
            f"one session wrote four successive brace-balancing heredocs "
            f"against it before giving up.",
            f"if you only need the VERDICT, read the sibling "
            f"`{_COMMAND_OUTPUT_STORE}/<cmd>.status.json` — one clean JSON "
            f"document carrying the same `status` the `CODEYAM_CMD_COMPLETE` "
            f"line does, already on disk. That read is NOT blocked and needs no "
            f"re-run, which matters when the original command was a `push`, a "
            f"`commit`, or a `session-finalize`. If you need the full document "
            f"instead, re-run the ORIGINAL command with `--format json` and "
            f"redirect stdout ALONE (`{cli_command()} editor <command> "
            f"--format json > report.json`). Under `--format json` the marker "
            f"lines move to stderr, the narrative falls silent, and terminal "
            f"output bounding is disabled, so the redirect is exact and "
            f"complete.",
        )
    if kind == "harness-tool-result":
        return (
            f"this carves a document out of a `tool-results/<id>.txt` file — "
            f"the HARNESS's own persisted capture of a command's terminal "
            f"output, saved because that output was too large to show inline. "
            f"It holds both streams in arrival order and is bounded for a "
            f"human reader, so it is not a JSON document: a brace-matcher or "
            f"an `rfind`/`re.search` over it either throws or silently returns "
            f"a FRAGMENT, and the fragment is the worse outcome because "
            f"nothing about it looks wrong.",
            f"read the document itself — it is almost certainly already on "
            f"disk and needs no re-run. Any `--format json` run of a wrapped "
            f"command also writes "
            f"`{_COMMAND_OUTPUT_STORE}/runs/<cmd>-<runId>.json`: the stdout "
            f"document ALONE, no stderr narrative, not terminal-bounded, and "
            f"keyed on the RUN so a later narrower re-run cannot clobber it. "
            f"The command named that exact path on its own "
            f"`CODEYAM_FULL_OUTPUT: … — PARSEABLE:` line, so `cat` what the "
            f"pointer printed. If you only need ONE finding rather than the "
            f"whole document, recompute it cheaply instead of mining a large "
            f"one: `{cli_command()} editor audit --only <INVARIANT_ID> "
            f"--format json` (pass `--only ?` to list the ids), or the "
            f"read-only query surface for the store in question "
            f"(`registry-query`, `evidence-query`, `glossary-list`, "
            f"`scenarios --format entries`, …), each of which emits one clean "
            f"document with its rows under `entries`.",
        )
    return (
        f"this builds on a journal entry named by a LITERAL timestamp. The "
        f"entry matching the active feature is not necessarily the one whose "
        f"filename was read off an `ls`, so this can silently land on another "
        f"feature's entry — you read that feature's fields believing they are "
        f"this one's, or you commit its description as this feature's body. "
        f"Either way the wrong entry is invisible in the result, which is why "
        f"the filename is not the selector and entry resolution exists.",
        f"pick by what you are doing with it — both resolve the ACTIVE "
        f"feature's entry, so neither needs a timestamp. TO READ THE ENTRY: "
        f"`{cli_command()} editor journal-show` prints its title, type, "
        f"description, and references; `--format json` emits the standard "
        f"query-surface envelope, so "
        f"`{cli_command()} editor journal-show --format json` parses with the "
        f"same `entries` key as every other read-only surface. TO BUILD THE "
        f"COMMIT: `{cli_command()} editor journal-commit-message` prints the "
        f"finished message on stdout and nothing else, so "
        f"`{cli_command()} editor journal-commit-message | git commit -F -` "
        f"needs no temp file; add `--trailer '<line>'` (repeatable) for "
        f"`Co-Authored-By:` / `Claude-Session:` lines. Both take "
        f"`--entry <path>` to override the resolution deliberately, and both "
        f"report on stderr which entry they chose and why.",
    )


def scripted_state_read_notice(store, inspector):
    """The pointer text for a scripted parse of a store that has an inspector.

    Distinct from `inspector_nudge`'s wording because the caller's problem is
    distinct: they are not merely reading the store, they are re-deriving its
    SCHEMA, and the answer is that the inspector emits one clean document
    under `--format json`."""
    return (
        f"NOTE: this hand-parses {store} — an internal codeyam state store whose "
        f"schema is internal and moves, so a parse that is right today reads wrong "
        f"the day the shape changes. `{cli_command()} editor {inspector}` answers "
        f"the question directly and emits ONE clean JSON document under "
        f"`--format json`, with the row set always under `entries`. Not blocking; "
        f"your command still runs."
    )


def classify_write_target(file_path, project_dir):
    """How the slug gate should treat a Write/Edit target: `("outside", None)`,
    `("editor-state", rel)`, or `("code", rel)`.

    Two bugs of the same shape lived in the substring test this replaces.

    A path OUTSIDE the repository is not a code change at all, so the slug gate
    has nothing to say about it. It used to refuse one anyway: at
    `slug=commit`, `Write <scratchpad>/commit-msg.txt` exited 2 while
    `cat > <scratchpad>/commit-msg.txt <<'EOF'` — the same write, through the
    shell — was allowed. Agents took the second path and said so. That inverts
    the very property CLAUDE.md's scripted-rewrite ban exists to protect: a
    `Write` shows its content as a structured field in the transcript, a
    heredoc makes a reviewer reconstruct it from a shell string. The
    neighbouring rule already carves out temp paths and advertises it
    ("Writing to an untracked file, to /tmp, or to the scratchpad is
    unaffected"); this gate made that sentence false.

    And because the escape was a SUBSTRING (`"/.codeyam/" in file_path`), it
    keyed on a LEADING SLASH: `Write .codeyam/editor.json` was refused while
    `Write /x/.codeyam/editor.json` was allowed. Comparing a normalized
    repo-relative prefix is what makes the relative spelling — the one actually
    used — work.

    Repo-membership, not tracked-ness, is the predicate: a brand-new source
    file at a gate slug IS a code change."""
    rel = _repo_relative(file_path, project_dir)
    if rel is None:
        return ("outside", None)
    normalized = rel.replace("\\", "/")
    if normalized.startswith((".codeyam/", ".claude/")):
        return ("editor-state", normalized)
    return ("code", normalized)


def preview_marker_state(marker_path, step):
    """`(preview_ok, observed)` for the preview gate — whether the marker at
    `marker_path` matches `step`, and a human-readable account of what was
    actually found there.

    The `observed` half is the point. The gate compares a marker step to the
    current step and used to name neither, so the only way to debug a refusal
    was to read this source — which is what agents did. The three not-ok
    states are genuinely different problems (never shown, corrupt, shown at a
    different step) and want different responses."""
    if not os.path.exists(marker_path):
        return (False, "file absent")
    try:
        with open(marker_path, "r") as f:
            marker = json.load(f)
    except Exception:
        return (False, "unreadable")
    found = marker.get("step")
    return (found == step, f"step {found!r}")


# The commands that WRITE the preview-shown marker, mirroring
# `preview_gate::marker_writing_command_sources`
# (crates/codeyam-editor/src/commands/editor/preview_gate.rs). Keep the two in
# agreement. Naming them turns "which command counts as showing a preview?"
# from a guess into a lookup — `recapture-stale` renders a preview and still
# writes no marker.
#
# `preview-verify` used to sit on that non-marking side and no longer does. It
# runs the same navigate+capture `preview` does and then asserts three gates
# over the result, so it was the STRONGEST evidence available that a preview
# had been shown while still leaving this gate shut — four sessions across four
# VMs each answered that by paying a redundant `preview` run whose only product
# was the marker. Anything moved between the two sides here must move in
# `marker_writing_command_sources` in the same change.
MARKER_WRITING_COMMANDS = (
    "preview",
    "preview-flow",
    "preview-html",
    "preview-interact",
    "preview-verify",
    "show-results",
)


def preview_required_next_action(observed, step, hint):
    """The `Next valid action:` text for a preview-gate refusal, routed by the
    discriminant [`preview_marker_state`] already returned.

    Its three not-ok states are different problems, and this gate used to emit
    ONE narrative for all of them: a pipe/SIGPIPE story that is provably not the
    cause on POSIX, where every marker-writing command runs under
    `run_with_liveness` (so it never sees EPIPE) and writes the marker before its
    first stdout write (pinned by `marker_is_written_before_any_stdout`). An
    agent hit it with an ABSENT marker, believed it, and copied the false
    diagnosis into its transcript. Each arm now describes the state it is in.

    The pipe warning survives only in the `unreadable` arm — a truncated marker
    is the one state where a severed write still explains the symptom, and
    `stream_capture` is `#[cfg(unix)]`, so a non-POSIX host can still reach it."""
    marking = ", ".join(f"`{c}`" for c in MARKER_WRITING_COMMANDS)
    if observed == "file absent":
        return (
            f"no preview has been shown at THIS step. The marker is cleared on "
            f"every `advance`, and only {marking} write it — `recapture-stale` "
            f"shows a preview but does NOT mark it. Run "
            f"`{hint}`, then call AskUserQuestion."
        )
    if observed == "unreadable":
        return (
            f"the marker exists but does not parse, so a write was cut short "
            f"mid-file. Check whether you piped `{hint}` into `head`/`tail`/"
            f"`grep`: that closes the pipe early and SIGPIPEs the command, so the "
            f"capture and the screenshots succeed but the marker write is lost. "
            f"Re-run it bare (no pipe)."
        )
    return (
        f"a preview was shown, but at a different step — the marker holds "
        f"{observed} and this is step {step}. Advancing clears it, so re-show it "
        f"HERE: run `{hint}`, then call AskUserQuestion."
    )


def describe_call(tool_name, tool_input):
    """A short, stable identifier for the call being judged.

    Folded into the repeat fingerprint so two DIFFERENT calls refused under one
    rule are not reported as "this exact call was refused before" — six of the
    eleven block sites used to pass only the slug, so three distinct `grep -P`
    commands escalated to a 3x repeat notice that was simply false."""
    if tool_name == "Bash":
        return f"Bash: {tool_input.get('command', '')}"
    file_path = tool_input.get("file_path", "")
    return f"{tool_name}: {file_path}" if file_path else tool_name


def main():
    """Claude Code PreToolUse hook entry point: read the current
    editor step from `.codeyam/editor-step.json` and either allow or
    block the in-flight tool call based on the active step's rules."""
    global _EXPLAIN_MODE
    # Set from argv ONCE, before any rule runs, and never read from the
    # environment or the event — see `_EXPLAIN_MODE`.
    _EXPLAIN_MODE = explain_requested(sys.argv[1:])

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Read the tool use event from stdin
    event = read_event()
    if event is None:
        allow("no parseable PreToolUse event on stdin")

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    call = describe_call(tool_name, tool_input)

    # Scripted-source-rewrite guard. Unlike every other rule here this one is
    # neither step-scoped nor editor-mode-scoped — the ban on machine-rewriting
    # tracked source holds in every session — so it fires before the
    # `CODEYAM_EDITOR_ACTIVE` short-circuit below.
    if tool_name == "Bash":
        found = scripted_rewrite_stage(tool_input.get("command", ""), project_dir)
        if found:
            rewrite_target, stage, stage_count, append_only = found
            reason, next_action = scripted_rewrite_refusal(rewrite_target, append_only)
            evidence = resolved_context(project_dir, "git ls-files")
            compound = compound_stage_evidence(stage, stage_count)
            if compound:
                evidence = f"{evidence}; {compound}"
            block(
                project_dir,
                "scripted-rewrite",
                reason,
                next_action,
                detail=rewrite_target,
                evidence=evidence,
                call=call,
            )

    # Scripted state-read guard. Neither step-scoped nor editor-mode-scoped,
    # for the same reason as the guard above: a commit body carrying another
    # feature's description is just as wrong outside the editor workflow, and
    # a parse of the command-output tee is just as impossible. It also has to
    # fire before the "always allow codeyam-editor editor" short-circuit
    # further down, which would otherwise exit 0 and skip both verdicts.
    #
    # `inspector_nudge` — the softer, editor-mode-only pointer — is reached
    # much further down and never doubles up with this: `notice` and `block`
    # both exit, so a command judged here never reaches it.
    if tool_name == "Bash":
        state_read = scripted_state_read_target(tool_input.get("command", ""))
        if state_read:
            kind, store, inspector = state_read
            if kind == "inspectable":
                notice("scripted-state-read", scripted_state_read_notice(store, inspector))
            reason, next_action = scripted_state_read_refusal(kind)
            block(
                project_dir,
                "scripted-state-read",
                reason,
                next_action,
                detail=store,
                evidence=(
                    f"the command parses JSON (`json.load`/`JSON.parse`/`jq`) and "
                    f"names `{store}`; no `.codeyam/` write construct present, so "
                    f"this is a read"
                ),
                call=call,
            )

    # Piped-gating-command guard. Neither step-scoped nor editor-mode-scoped,
    # for the same reason as the guard above: the rule holds in every session.
    # It also has to fire before the "always allow codeyam-editor editor"
    # short-circuit further down, which would otherwise exit 0 silently and
    # skip the pointer.
    #
    # This is an ADVISORY now, not a refusal. Every gating subcommand runs
    # inside the liveness bracket, which makes a pipe cost the terminal display
    # and the shell exit code — both recoverable from the two sidecars the
    # notice names — instead of costing the command. Where the bracket's capture
    # does not exist, the original harms are all still live and so is the block.
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        piped = piped_gating_command(command)
        if piped:
            if not _capture_available():
                block(
                    project_dir,
                    "piped-gating-command",
                    f"this pipes `{cli_command()} editor {piped}` into a filter "
                    f"on a host with no stream capture, so the command writes "
                    f"straight to your pipe. A filter that stops reading kills "
                    f"it mid-run, and there is no transcript or status document "
                    f"to recover the output or the verdict from.",
                    f"run it BARE and read the verdict off its own terminal line "
                    f"(`CODEYAM_VERIFY_BUILD: PASS|FAIL`, the "
                    f"`CODEYAM_CMD_COMPLETE` `status`). `| tee out.txt` is the "
                    f"one filter that costs nothing.",
                    detail=piped,
                    evidence=(
                        f"`{piped}` is in the gating-subcommand set; "
                        f"os.name={os.name!r} has no `#[cfg(unix)]` stream "
                        f"capture; `| tee` not present"
                    ),
                    call=call,
                )
            notice("piped-gating-command", piped_gating_notice(piped))

    # Recursive-delete guard. Neither step-scoped nor editor-mode-scoped, for
    # the same reason as the two above: `rm -rf` over tracked files is a loss in
    # any session, and the damage does not surface until a later `git status`.
    if tool_name == "Bash":
        deletion = tracked_recursive_rm(tool_input.get("command", ""), project_dir)
        if deletion:
            target, tracked_count = deletion
            reason, next_action = recursive_rm_refusal(target, tracked_count)
            block(
                project_dir,
                "recursive-delete",
                reason,
                next_action,
                detail=target,
                evidence=(
                    f"{resolved_context(project_dir, 'git ls-files')}; "
                    + (
                        "segment could not be tokenized"
                        if tracked_count is None
                        else f"`git ls-files -- {target}` reports {tracked_count} tracked file(s)"
                    )
                ),
                call=call,
            )

    # Self-matching-pgrep guard. Neither step-scoped nor editor-mode-scoped,
    # for the same reason as the guards above: a wait loop that polls for its
    # own argv hangs in any session, and it hangs silently — an agent inside
    # one has no turn left in which to notice.
    #
    # It sits LAST among the unscoped guards deliberately. `notice` exits 0, so
    # whichever verdict fires first is the only one emitted, and an advisory
    # about a command that merely will not finish must never displace a refusal
    # about a command that destroys something.
    if tool_name == "Bash":
        pgrep_pattern = self_matching_pgrep_loop(tool_input.get("command", ""))
        if pgrep_pattern:
            notice("self-matching-pgrep", self_matching_pgrep_notice(pgrep_pattern))

    # Every remaining rule is a workflow-step gate — only enforce in editor mode
    if not os.environ.get("CODEYAM_EDITOR_ACTIVE"):
        allow("CODEYAM_EDITOR_ACTIVE unset — step gates do not apply")

    state_path = os.path.join(project_dir, ".codeyam", "editor-step.json")

    # No state file = not in editor mode, allow everything
    if not os.path.exists(state_path):
        allow(f"no step state at {state_path} — not in editor mode")

    try:
        with open(state_path, "r") as f:
            state = json.load(f)
    except (json.JSONDecodeError, IOError):
        allow(f"step state at {state_path} is unreadable — degrading to allow")

    step = state.get("step", 0)
    slug = state.get("slug") or ""

    if not step:
        allow(f"step state at {state_path} carries no step number")

    metadata = load_step_metadata(project_dir)
    mode, mode_table = resolve_mode_table(state, metadata)

    code_change_slugs = set(mode_table.get("codeChangeSlugs", []))
    commit_slugs = set(mode_table.get("commitSlugs", []))
    push_slugs = set(mode_table.get("pushSlugs", []))
    preview_required_slugs = set(mode_table.get("previewRequiredSlugs", []))
    test_run_slugs = set(mode_table.get("testRunSlugs", []))
    no_test_slugs = mode_table.get("noTestSlugs", {}) or {}

    # Always allow codeyam-editor commands. Match both the canonical
    # name and the local-dev wrapper so saved sessions emitted under
    # either spelling keep working after the canonical-name rollout.
    if tool_name == "Bash":
        command = tool_input.get("command", "")

        # Test-run gate. `testRunSlugs` is the per-mode set of slugs whose
        # phase declares a non-None test_scope — a slug NOT in it may not run
        # tests. This must fire BEFORE the "always allow codeyam-editor editor"
        # short-circuit below, because `codeyam-editor editor refresh-tests` is
        # itself a test run. Empty `testRunSlugs` (a stale v1/v2 cache) => no
        # gating, mirroring the `and commit_slugs` / `and push_slugs`
        # short-circuits below — a cache skew degrades to "allow", never "block
        # every test run".
        #
        # The MEMBERSHIP test is one line; wording the refusal is not, because
        # a blocked slug can be pre-Demo or post-hardening and the two need
        # opposite advice. `_test_run_block_message` reads that from the
        # `noTestSlugs` projection.
        if (
            slug
            and test_run_slugs
            and slug not in test_run_slugs
            and is_test_run_command(command, project_dir)
        ):
            reason, next_action = _test_run_block_message(
                state, slug, no_test_slugs.get(slug)
            )
            kind = (no_test_slugs.get(slug) or {}).get("kind") or "unclassified"
            block(
                project_dir,
                "test-run",
                reason,
                next_action,
                detail=slug,
                evidence=(
                    f"{resolved_context(project_dir, state_path)}; slug `{slug}` "
                    f"(kind {kind}) is not in testRunSlugs"
                ),
                call=call,
            )

        # Inspector nudge. Emitted on stderr and then FALLEN THROUGH from
        # — never `sys.exit`ed on — so the command still runs and every
        # gate below still applies. stderr is the channel every other
        # message in this hook uses; pairing it with a 0 exit is what
        # makes this a pointer rather than a refusal.
        nudge = inspector_nudge(command)
        if nudge:
            print(nudge, file=sys.stderr)

        # Position-aware, unlike the substring test it replaces: a command that
        # merely MENTIONS the CLI — most of all inside a quoted commit message —
        # used to short-circuit the commit, push, code-change and PCRE gates
        # below. See `invokes_codeyam_editor`.
        if invokes_codeyam_editor(command):
            allow("runs a `codeyam-editor editor` subcommand")

    # Always allow reading
    if tool_name in ("Read", "Glob", "Grep", "WebFetch", "WebSearch", "Agent"):
        allow(f"{tool_name} is a read-only tool")

    # Always allow task management
    if tool_name in ("TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "Skill", "ToolSearch"):
        allow(f"{tool_name} is workflow/task management")

    # Gate AskUserQuestion at preview-required slugs — require preview marker first
    if tool_name == "AskUserQuestion":
        if slug and slug in preview_required_slugs:
            marker_path = os.path.join(project_dir, ".codeyam", "preview-shown.json")
            preview_ok, observed = preview_marker_state(marker_path, step)

            if not preview_ok:
                hint = _preview_hint(mode, project_dir)
                block(
                    project_dir,
                    "preview-required",
                    f"This step ({_slug_label(state, slug)}) requires showing "
                    f"the live preview before asking the user for confirmation.",
                    preview_required_next_action(observed, step, hint),
                    detail=slug,
                    evidence=(
                        f"{resolved_context(project_dir, marker_path)}; marker "
                        f"holds {observed}, this step is {step}"
                    ),
                    call=call,
                )

        allow("AskUserQuestion with the preview requirement satisfied")

    # Check Write/Edit to non-.codeyam files
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")

        # `@import url(...)` in CSS is render-blocking and bypasses Next.js's
        # font pipeline. Webfonts belong in layout.tsx via next/font or a
        # <link rel="preconnect"> + <link href> — check BEFORE the .codeyam/
        # short-circuit so authored CSS is gated regardless of step.
        if file_path.endswith(".css"):
            content_str = tool_input.get("content", "") or tool_input.get("new_string", "")
            if "@import url" in content_str:
                block(
                    project_dir,
                    "css-import-url",
                    "`@import url(...)` in CSS is render-blocking and hurts LCP.",
                    "load the webfont via next/font in layout.tsx (or a "
                    "<link rel=\"preconnect\"> + <link href> pair), then re-apply "
                    "this edit without the `@import url(...)` line.",
                    detail=file_path,
                    evidence=f"`@import url` found in the {tool_name} payload for {file_path}",
                    call=call,
                )

        # A line-budgeted file is checked BEFORE the `.claude/` short-circuit
        # below, for the same reason the CSS rule is: the guarded file lives
        # under `.claude/`, so a gate placed after that short-circuit would never
        # fire on the one file it exists for. This is not step-scoped either —
        # the budget holds at every slug, editor mode or not.
        violation = line_budget_violation(tool_name, tool_input, project_dir)
        if violation:
            rel, limit, current, projected = violation
            reason, next_action = line_budget_refusal(rel, limit, current, projected)
            block(
                project_dir,
                "line-budget",
                reason,
                next_action,
                detail=rel,
                evidence=(
                    f"{resolved_context(project_dir, rel)}; budget {limit} lines, "
                    f"currently {current}, this edit makes it {projected}"
                ),
                call=call,
            )

        # Target-path model, replacing a pair of substring tests — see
        # `classify_write_target` for the two bugs that lived here.
        placement, normalized_target = classify_write_target(file_path, project_dir)
        if placement == "outside":
            allow(f"{file_path} resolves outside {project_dir} — not a code change")
        if placement == "editor-state":
            allow(f"{normalized_target} is editor state, writable at every slug")
        # Empty allowlist means the cache is missing/stale (e.g. a v1
        # cache after a binary downgrade) — degrade to "allow" rather
        # than brick the session. An empty `slug` means the state file
        # predates the slug field; the next `editor step` invocation
        # will migrate it, so degrade to "allow" rather than block on
        # an unmatchable allowlist.
        # Resolving a conflict is not authoring a feature. `pre-commit-sync`
        # starts a rebase and, on a genuine source conflict, prints a recovery
        # that reads "resolve each file, `git add` it, then `git rebase
        # --continue`" — which this gate then refused, wedging the very step
        # that printed it, with no in-band way out. The `git add` half already
        # carries exactly this escape (see merge_in_progress); the EDIT that
        # must precede it did not, so only half the recovery was reachable.
        # Scope is narrow: it opens only while a rebase/merge/cherry-pick is
        # PAUSED mid-operation, and `git commit` stays gated by its own slug
        # check regardless, so this cannot land a commit outside the commit
        # slug — it only lets an in-flight integration be finished.
        if (
            slug
            and code_change_slugs
            and slug not in code_change_slugs
            and not merge_in_progress(project_dir)
        ):
            allowed = ", ".join(sorted(code_change_slugs))
            # The list of permitted slugs is REFERENCE, deliberately below
            # both contract lines. Led with, it reads as a set to reason
            # about — which is how this block came to be the most-retried
            # one in the transcripts (four in a row at `backend-journal`).
            # One named command reads as an instruction to follow.
            block(
                project_dir,
                "code-change",
                f"This step ({_slug_label(state, slug)}) does not allow code changes.",
                f"run `{cli_command()} editor change` to reopen the build loop — "
                f"it MOVES the workflow cursor back to the nearest earlier slug "
                f"that permits edits and prints the command to return here — "
                f"then make this edit.",
                reference=f"Code changes are allowed at slugs: {allowed}.",
                detail=f"{slug}\x00{file_path}",
                evidence=(
                    f"{resolved_context(project_dir, state_path)}; target "
                    f"resolves to `{normalized_target}` INSIDE the repo; slug "
                    f"`{slug}` is not in codeChangeSlugs"
                ),
                call=call,
            )

    # Check Bash commands for git commit/push
    if tool_name == "Bash":
        command = tool_input.get("command", "")

        # `-P` (PCRE) is a GNU extension; BSD grep on macOS has no such flag.
        # This repo is developed on macOS laptops and run on Linux VMs, so the
        # rule is about PORTABILITY, not about the current host — it fires on
        # every platform, and the message must therefore stay true on every
        # platform. Do not reintroduce a claim about which OS is running: the
        # block previously asserted the host was macOS and fired inside Linux
        # containers, which teaches an agent to distrust the hook's other
        # explanations.
        if _uses_pcre_grep(command):
            block(
                project_dir,
                "grep-p",
                "`grep -P` (PCRE) is not portable — BSD grep on macOS has no "
                "`-P`, so a command written on a Linux VM fails on a "
                "developer's laptop. The rule applies on every platform.",
                "use the Grep tool instead — it wraps ripgrep and honors "
                "PCRE syntax on both platforms.",
                evidence=f"a PCRE flag was found on a `grep` in command position in: {command}",
                call=call,
            )

        # Each of these three used to be a bare `"git <verb>" in command`
        # substring test, so a mere MENTION of the verb was refused —
        # `echo "remember to git commit later"` at a plan slug, and any commit
        # whose own message discussed committing. `invokes_git_subcommand`
        # asks whether the verb is what the command RUNS.
        if invokes_git_subcommand(command, "commit"):
            if slug and commit_slugs and slug not in commit_slugs and not staged_paths_are_plans_only(project_dir):
                allowed = ", ".join(sorted(commit_slugs))
                block(
                    project_dir,
                    "git-commit",
                    f"git commit is only allowed at slug(s): {allowed}. "
                    f"You are at {_slug_label(state, slug)}.",
                    "keep following the workflow — `codeyam-editor editor advance` "
                    f"until the {_commit_gate_phrase(commit_slugs)} slug, which commits for you. "
                    "If this commit genuinely belongs OUTSIDE the workflow (re-triggering a "
                    "stalled deploy, a release pass), advancing the whole workflow is not a "
                    "route to that goal — run `codeyam-editor editor commit --out-of-workflow "
                    '-m "<msg>"` instead (add `--allow-empty` for an empty commit). It runs the '
                    "static-check and test-cache gates itself before committing, and is the "
                    "gated replacement for `git commit --no-verify`, which skips every gate. "
                    "To read what "
                    "a later slug requires without moving the workflow pointer, run "
                    "`codeyam-editor editor step --show --slug <slug>`.",
                    reference="Plan-file commits (.codeyam/plans/*.md) are allowed at any step.",
                    detail=slug,
                    evidence=(
                        f"{resolved_context(project_dir, state_path)}; `git commit` "
                        f"is in command position; staged set is not plans-only"
                    ),
                    call=call,
                )
        elif invokes_git_subcommand(command, "add"):
            if (
                slug
                and commit_slugs
                and slug not in commit_slugs
                and not git_add_paths_are_plans_only(command)
                and not merge_in_progress(project_dir)
            ):
                allowed = ", ".join(sorted(commit_slugs))
                block(
                    project_dir,
                    "git-add",
                    f"git add is only allowed at slug(s): {allowed}. "
                    f"You are at {_slug_label(state, slug)}.",
                    f"leave staging to the workflow — the {_commit_gate_phrase(commit_slugs)} slug runs "
                    "`codeyam-editor editor stage-feature`, which stages this for you.",
                    reference="Plan-file commits (.codeyam/plans/*.md) are allowed at any step, "
                    "and `git add` is permitted while a rebase/merge is paused mid-operation.",
                    detail=slug,
                    evidence=(
                        f"{resolved_context(project_dir, state_path)}; `git add` is in "
                        f"command position; paths are not plans-only; no rebase/merge "
                        f"is paused"
                    ),
                    call=call,
                )

        if invokes_git_subcommand(command, "push"):
            if slug and push_slugs and slug not in push_slugs:
                allowed = ", ".join(sorted(push_slugs))
                block(
                    project_dir,
                    "git-push",
                    f"git push is only allowed at slug(s): {allowed}. "
                    f"You are at {_slug_label(state, slug)}.",
                    "keep advancing to the `push` slug, which runs "
                    "`codeyam-editor editor push` with the queue held.",
                    detail=slug,
                    evidence=(
                        f"{resolved_context(project_dir, state_path)}; `git push` is "
                        f"in command position; slug `{slug}` is not in pushSlugs"
                    ),
                    call=call,
                )

    # Allow everything else
    allow("no gate matched this call")


if __name__ == "__main__":
    main()
