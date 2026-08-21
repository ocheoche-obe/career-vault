"""Latency recording for the integration suite (ADR-047).

The suite *records* every timing it takes and *asserts* only against a regression ceiling set well
above the requirement. That split is deliberate: gating on the NFR itself would ship a suite that is
red on arrival, and a suite that is always red says nothing when it goes red for a new reason. The
NFR verdict is a human reading the printed table; the ceiling only catches drift.

Each operation is measured three ways, and they are **never averaged together**:

``observed``
    Client wall-clock for the round trip. What a user would feel — and what also contains the
    caller's own DNS, TLS and credential-resolution costs on the first call of a process.

``lambda``
    What the Lambda says it spent, read from the REPORT line. Excludes everything on the wire.

``init``
    Container initialisation, present in the REPORT line **only on a cold start**. This is the
    authoritative cold/warm signal; inferring one from wall-clock time cannot distinguish a cold
    Lambda from a cold boto3 client, and those have completely different fixes.

The first call and the steady-state repeats are recorded as separate rows, because a first call and
a warm one are different operations that happen to share a name, and their mean describes neither.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Sample:
    """One recorded measurement."""

    name: str
    tier: str
    kind: str  # "first-call" | "steady-state"
    ms: float
    lambda_ms: float | None = None
    init_ms: float | None = None
    nfr: str | None = None
    nfr_ms: int | None = None
    ceiling_ms: int | None = None
    notes: str = ""

    @property
    def captured(self) -> bool:
        """False for a deliberately-recorded NaN meaning "attempted, not captured"."""
        return self.ms == self.ms

    @property
    def over_nfr(self) -> bool:
        return self.captured and self.nfr_ms is not None and self.ms > self.nfr_ms

    @property
    def over_ceiling(self) -> bool:
        return self.captured and self.ceiling_ms is not None and self.ms > self.ceiling_ms

    @property
    def verdict(self) -> str:
        if not self.captured:
            return "—"
        if self.nfr_ms is None:
            return "—"
        return "PASS" if not self.over_nfr else "OVER NFR"


def _ms(value: float | None) -> str:
    if value is None:
        return "—"
    if value != value:  # NaN — recorded deliberately to mean "attempted, not captured"
        return "not captured"
    return f"{value:,.0f} ms"


def _init_cell(sample: "Sample") -> str:
    """Init duration, or why there isn't one.

    Three distinct states that must not collapse into each other: a cold start (the number), a
    confirmed warm container (no Init Duration in a REPORT line we *did* read), and no Lambda report
    at all (nothing was read, so warm/cold is unknown).
    """
    if sample.init_ms is not None:
        return _ms(sample.init_ms)
    return "warm" if sample.lambda_ms is not None else "—"


@dataclass
class LatencyLog:
    """Session-wide collector. Printed once by ``pytest_terminal_summary``."""

    samples: list[Sample] = field(default_factory=list)

    def add(self, sample: Sample) -> None:
        self.samples.append(sample)

    def measure(
        self,
        call: Callable[[], object],
        *,
        name: str,
        tier: str,
        nfr: str | None = None,
        nfr_ms: int | None = None,
        ceiling_ms: int | None = None,
        repeats: int = 3,
        report_of: Callable[[object], object] | None = None,
    ) -> list[object]:
        """Time ``call`` once, then ``repeats`` more times, recording both kinds.

        ``report_of`` optionally extracts a ``Report`` (see ``_helpers.invoke_timed``) from each
        result, which is what fills the ``lambda`` and ``init`` columns.

        Returns every result so the caller can still assert on *what* came back — a latency test
        that stops checking correctness is measuring the speed of an unknown operation.

        The regression ceiling is enforced *here*, after the samples are recorded, rather than left
        to each caller. Two reasons: a check the caller has to remember is a check that eventually
        gets forgotten, and recording before asserting means a breach still appears in the printed
        table instead of vanishing with the failure.
        """
        results: list[object] = []
        first_index = len(self.samples)

        def report_for(result: object) -> tuple[float | None, float | None]:
            if report_of is None:
                return None, None
            report = report_of(result)
            return report.get("duration_ms"), report.get("init_ms")  # type: ignore[union-attr]

        started = time.perf_counter()
        first_result = call()
        first_ms = (time.perf_counter() - started) * 1000
        results.append(first_result)
        first_lambda, first_init = report_for(first_result)

        self.add(
            Sample(
                name=name,
                tier=tier,
                kind="first-call",
                ms=first_ms,
                lambda_ms=first_lambda,
                init_ms=first_init,
                nfr=nfr,
                nfr_ms=nfr_ms,
                ceiling_ms=ceiling_ms,
            )
        )

        # Paired, so the row stays internally coherent. Taking each column's median independently
        # produces an observed round trip that does not contain its own reported Lambda duration,
        # because the two numbers then come from different calls — the same defect that made the
        # first cold-start row read as a 1,265 ms request containing 2,112 ms of work.
        repeats_seen: list[tuple[float, float | None]] = []
        for _ in range(repeats):
            started = time.perf_counter()
            result = call()
            elapsed_ms = (time.perf_counter() - started) * 1000
            results.append(result)
            lambda_ms, _init = report_for(result)
            repeats_seen.append((elapsed_ms, lambda_ms))

        if repeats_seen:
            repeats_seen.sort(key=lambda pair: pair[0])
            median_ms, median_lambda = repeats_seen[len(repeats_seen) // 2]
            self.add(
                Sample(
                    name=name,
                    tier=tier,
                    kind="steady-state",
                    ms=median_ms,
                    lambda_ms=median_lambda,
                    init_ms=None,
                    nfr=nfr,
                    nfr_ms=nfr_ms,
                    ceiling_ms=ceiling_ms,
                )
            )

        breached = [sample for sample in self.samples[first_index:] if sample.over_ceiling]
        if breached:
            import pytest

            pytest.fail(
                "regression ceiling breached: "
                + ", ".join(
                    f"{s.name} [{s.kind}] {s.ms:,.0f} ms > {s.ceiling_ms:,} ms" for s in breached
                )
            )

        return results

    def record(self, **fields) -> Sample:
        """Record a single measurement the ``measure`` loop cannot express.

        Cold starts are the motivating case: they cannot be produced by calling something repeatedly
        (repetition is what makes a container warm), so they are gathered by a concurrent burst and
        handed here already summarised.
        """
        sample = Sample(**fields)
        self.add(sample)
        # Enforced here too, not only in `measure`. Storing a `ceiling_ms` that nothing checks is a
        # gate that cannot fail — the cold-start row and the ~$0.11 résumé row both carried one, and
        # the terminal summary printed the breach banner while the suite exited 0.
        if sample.over_ceiling:
            import pytest

            pytest.fail(
                f"regression ceiling breached: {sample.name} [{sample.kind}] "
                f"{sample.ms:,.0f} ms > {sample.ceiling_ms:,} ms"
            )
        return sample

    def breaches(self) -> list[Sample]:
        return [s for s in self.samples if s.over_ceiling]


#: Module-level singleton. The terminal-summary hook runs outside any fixture, so the log has to be
#: reachable without one; a test harness is the one place this beats threading it through.
LOG = LatencyLog()


def format_table(samples: list[Sample]) -> list[str]:
    """Render the recorded samples as aligned lines, or one line saying nothing ran."""
    if not samples:
        return ["  (no latency samples recorded — the tiers that measure them did not run)"]

    header = ("Measurement", "Kind", "Observed", "Lambda", "Init", "NFR", "Budget", "Verdict", "Notes")
    rows = [
        (
            s.name,
            s.kind,
            _ms(s.ms),
            _ms(s.lambda_ms),
            _init_cell(s),
            s.nfr or "—",
            _ms(s.nfr_ms),
            s.verdict,
            s.notes,
        )
        for s in samples
    ]

    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]

    def line(cells) -> str:
        return "  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    out = [line(header), "  " + "  ".join("-" * w for w in widths)]
    out.extend(line(r) for r in rows)
    return out
