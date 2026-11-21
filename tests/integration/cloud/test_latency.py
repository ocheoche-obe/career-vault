"""Latency of the interactive paths, measured against the deployed stack (ADR-047, B-023).

Free tier: no model is called here. The dashboard read is the one interactive path measurable
honestly without spending anything — ``GET /entries`` makes no Bedrock call at all, reading DynamoDB
and stripping the embeddings before it responds.

NFR-2.1 (ingestion) is *not* here. "End-to-end" includes the Haiku parse turn, so timing it in this
tier would measure everything except the dominant term — a green number that omits the slow step is
worse than no number, because it looks like evidence. It lives in the ``bedrock`` tier.

**Test order in this file is load-bearing.** The empty-corpus control runs first so that it, not the
measurement we care about, pays for boto3 client construction, SSO credential resolution, DNS and
the TLS handshake. Those costs are real but they are the *test process's*, not the app's, and they
land entirely on whichever call happens to go first.
"""

from __future__ import annotations

import pytest

from _helpers import api_event, body_of, invoke_timed, seed_entries

pytestmark = pytest.mark.cloud

#: The corpus the real user actually has (13 entries at slice 9), so the recorded number describes
#: the app as it is rather than an empty account. B-013's read cost scales with this number.
REALISTIC_CORPUS = 13

#: Regression ceiling, deliberately far above NFR-2.3's 2000 ms budget. A gate at the requirement
#: would fire on any cold start and teach everyone to ignore it; see ADR-047 for why this asserts
#: drift rather than compliance.
DASHBOARD_CEILING_MS = 10_000


class TestDashboardLoad:
    """NFR-2.3 — "dashboard initial load shall complete within 2 seconds"."""

    def test_an_empty_corpus_is_measured_first_as_the_b013_control(
        self, lambda_client, cleanup_user, latency
    ):
        """The same read with nothing to read.

        This is the control for B-013: the difference between this and the 13-entry measurement is
        the part of dashboard latency that *scales with the corpus*, which is the part that gets
        worse as the app is used as intended and the only part a B-013 fix could move.
        """
        results = latency.measure(
            lambda: invoke_timed(
                lambda_client, "career_crud", api_event(method="GET", user_id=cleanup_user)
            ),
            name="GET /entries — empty corpus (control)",
            tier="cloud",
            nfr="NFR-2.3",
            nfr_ms=2_000,
            ceiling_ms=DASHBOARD_CEILING_MS,
            report_of=lambda result: result[1],
        )

        for response, _report in results:
            assert response["statusCode"] == 200
            assert body_of(response)["entries"] == []

    def test_a_realistic_corpus_is_measured_against_nfr_2_3(
        self, lambda_client, live_table, cleanup_user, latency
    ):
        seeded = seed_entries(live_table, cleanup_user, REALISTIC_CORPUS)

        results = latency.measure(
            lambda: invoke_timed(
                lambda_client, "career_crud", api_event(method="GET", user_id=cleanup_user)
            ),
            name=f"GET /entries — {REALISTIC_CORPUS} entries",
            tier="cloud",
            nfr="NFR-2.3",
            nfr_ms=2_000,
            ceiling_ms=DASHBOARD_CEILING_MS,
            report_of=lambda result: result[1],
        )

        # A latency test that stops checking correctness is timing an unknown operation.
        for response, _report in results:
            assert response["statusCode"] == 200
            listed = body_of(response)["entries"]
            assert len(listed) == len(seeded)
            # If this ever fails, the number above is measuring a *different*, lighter operation:
            # ADR-016's vector is read from DynamoDB and stripped here (B-013), not left unread.
            assert "embedding" not in listed[0]


class TestColdStart:
    """The cold path, which for this app is the *normal* path.

    CareerVault has one user and sits idle most of the day, so the dashboard load that matters is
    almost always the first one after a gap — a cold container. Measuring only warm invocations
    would produce a flattering number describing a situation the user is rarely in.

    A cold start cannot be produced by calling something repeatedly, since repetition is precisely
    what warms it. It is forced here by a **concurrent burst**: ``career_crud`` runs at reserved
    concurrency 5 (``samconfig.toml``, ADR-030), and only one or two containers are warm at any
    moment, so simultaneous callers beyond that get fresh ones. The burst stays under the reserved
    limit so the test cannot throttle itself.

    Nothing is mutated to achieve this. The alternative — an ``update_function_configuration`` call
    to invalidate the warm pool — would work but writes to the deployed dev stack, which *is* the
    MVP stack (ADR-041), to obtain a test measurement.
    """

    #: The reserved-concurrency ceiling for ``career_crud`` (``samconfig.toml``). Bursting *to* the
    #: cap is the most containers that can exist at once, which is the best available odds of
    #: exceeding the warm pool. It also means the measurement is inherently opportunistic: if five
    #: containers are already warm — which an earlier test file in the same session can arrange —
    #: no burst can force a cold one, and that is a property of Lambda, not a bug here.
    BURST = 5

    #: Bursts to attempt before giving up, with a pause between. Containers are not reclaimed on any
    #: schedule we control, so this improves the odds rather than guaranteeing anything.
    ATTEMPTS = 2

    def test_cold_start_init_duration_is_recorded(self, lambda_client, live_table, cleanup_user, latency):
        import time
        from concurrent.futures import ThreadPoolExecutor

        seed_entries(live_table, cleanup_user, REALISTIC_CORPUS)
        event = api_event(method="GET", user_id=cleanup_user)

        def one() -> tuple[dict, object, float]:
            started = time.perf_counter()
            response, report = invoke_timed(lambda_client, "career_crud", event)
            return response, report, (time.perf_counter() - started) * 1000

        cold: list[tuple[object, float]] = []
        for attempt in range(self.ATTEMPTS):
            with ThreadPoolExecutor(max_workers=self.BURST) as pool:
                outcomes = list(pool.map(lambda _: one(), range(self.BURST)))

            for response, _report, _elapsed in outcomes:
                assert response["statusCode"] == 200

            cold = [(r, e) for _resp, r, e in outcomes if r.get("init_ms") is not None]
            if cold:
                break
            if attempt + 1 < self.ATTEMPTS:
                time.sleep(2)

        if not cold:
            # Recorded as a row rather than only skipped, so the table cannot quietly lose a
            # measurement and read as though the cold path were fine.
            latency.record(
                name=f"GET /entries — {REALISTIC_CORPUS} entries",
                tier="cloud",
                kind="cold-start",
                ms=float("nan"),
                nfr="NFR-2.3",
                nfr_ms=2_000,
            )
            pytest.skip(
                f"{self.ATTEMPTS} bursts of {self.BURST} hit only warm containers — a cold start "
                "cannot be forced once the pool is full at reserved concurrency. Re-run alone "
                "(`-k cold_start`) to capture it."
            )

        # One representative invocation, not a median per column. Taking each column's median
        # independently produced an incoherent row on the first run — an observed round trip
        # *shorter* than the init plus duration it supposedly contains, because the three numbers
        # came from three different invocations. The median-by-observed sample is reported whole.
        cold.sort(key=lambda pair: pair[1])
        report, observed_ms = cold[len(cold) // 2]

        latency.record(
            name=f"GET /entries — {REALISTIC_CORPUS} entries",
            tier="cloud",
            kind="cold-start",
            ms=observed_ms,
            lambda_ms=report["duration_ms"],
            init_ms=report["init_ms"],
            nfr="NFR-2.3",
            nfr_ms=2_000,
            ceiling_ms=DASHBOARD_CEILING_MS,
        )
