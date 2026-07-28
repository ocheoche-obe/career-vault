#!/usr/bin/env bash
# PostToolUse / PostToolUseFailure hook (Bash matcher): enforce that a test run came out GREEN.
#
# Why this exists: wrap-slice's "tests must pass" gate is only as good as whether the tests were
# actually run and actually passed. Instructions can't self-enforce that; this hook can. It fires
# after any Bash command, ignores everything that isn't a test run, and for a test run it blocks
# (exit 2, feedback to Claude) unless the output clearly shows a green pytest summary. "Couldn't
# tell if it was green" is treated as not-green on purpose — that's the failure mode we're guarding.
#
# Registered on BOTH PostToolUse (fires on a passing command) and PostToolUseFailure (fires when the
# command exits non-zero, i.e. red tests), so either outcome is inspected with the same logic.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null)

# Only act on an actual *invocation* of the suite: the runner (optionally behind VAR=val prefixes)
# at the start of a command line. This deliberately ignores commands that merely *mention* the
# runner inside a string argument — e.g. a `git commit` whose message references pytest, which a
# naive substring match would wrongly flag.
_runner_re='^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+)*((\./|bash[[:space:]]+)?(scripts/)?run-tests\.sh|(python[0-9.]*[[:space:]]+-m[[:space:]]+)?pytest)([[:space:]]|$)'
if ! printf '%s\n' "$cmd" | grep -Eq "$_runner_re"; then
  exit 0
fi

# Stringify whatever shape tool_response has (object with stdout/stderr, or a string) so we can scan
# the captured output for pytest's summary line regardless of the exact schema.
resp=$(printf '%s' "$input" | jq -r '.tool_response | tostring' 2>/dev/null)

# Green = a "<n> passed" summary is present AND no failure/error/empty-run signals are. The failure
# patterns are anchored to pytest's own summary phrasing ("<n> failed", "<n> error(s)", collection
# errors, "no tests ran") so a benign word like "warning" or an "error" inside a log line can't
# false-trip it.
if printf '%s' "$resp" | grep -Eq '[0-9]+ passed' \
   && ! printf '%s' "$resp" | grep -Eqi '[0-9]+ (failed|error(s)?)|no tests ran|errors during collection'; then
  exit 0
fi

echo "Test run did NOT come out clearly green. Do not treat the tests as passing — this is the \
wrap-slice gate. Re-run ./scripts/run-tests.sh, fix any failure/collection error, and confirm the \
summary shows only 'passed' (no 'failed'/'error') before continuing." >&2
exit 2
