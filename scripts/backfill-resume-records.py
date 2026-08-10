#!/usr/bin/env python3
"""One-time backfill: build durable RESUME# records from existing RESUMERUN# traces (ADR-046).

**Why this exists.** ADR-046 split résumé history into a durable ``RESUME#`` record and a 30-day
``RESUMERUN#`` trace, and the worker writes both from that point on. Runs that completed *before*
the split have only a trace — so they are invisible to ``GET /resumes``, and once their TTL fires
the S3 artifacts they point at become unreachable: no record to list them, no trace to poll, and
(since ADR-046 removed the ``resumes/`` lifecycle rule) nothing to clean them up either.

That gives the backfill a real deadline — the traces' own ``expires_at``. Run it before then.

**Safety properties**, in the order they matter:

- **Dry-run by default.** Writing requires ``--apply``. The dry run prints exactly what would be
  written.
- **Idempotent.** Writes go through ``create_resume_record`` → ``put_item_scoped``, which carries
  ``attribute_not_exists(SK)``. Re-running skips anything already backfilled instead of overwriting
  it, so a half-finished run is resumed simply by running it again.
- **Additive only.** It never modifies or deletes a trace. If the backfill is wrong, delete the
  ``RESUME#`` items and re-run; the source data is untouched.
- **Completed runs only.** Matching the worker: a failed or pending run gets no history row, and one
  missing its S3 keys is skipped rather than written as a record pointing at nothing.

Usage::

    AWS_PROFILE=careervault-dev python scripts/backfill-resume-records.py --user <cognito-sub>
    AWS_PROFILE=careervault-dev python scripts/backfill-resume-records.py --user <cognito-sub> --apply

``elapsed_seconds`` is deliberately absent from backfilled records: it did not exist when these runs
executed, and inventing a number for "how long did this take" would be fabricating a measurement
(the B-015 precedent). Consumers must treat it as optional.
"""

from __future__ import annotations

import argparse
import os
import sys

# The shared layer lives outside the scripts dir; mount it the way the Lambda runtime does.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "shared", "python"))

import boto3  # noqa: E402
from boto3.dynamodb.conditions import Key  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from careervault.ddb_helpers import create_resume_record, from_ddb_numbers  # noqa: E402

TABLE_NAME = os.environ.get("CAREERVAULT_TABLE_NAME", "CareerVaultTable-dev")
# `careervault.ddb_helpers.get_table` reads this from the environment (it normally runs inside a
# Lambda where SAM sets it). Export it so the shared helper and this script cannot disagree about
# which table is being written — a mismatch here writes real records into the wrong place.
os.environ["CAREERVAULT_TABLE_NAME"] = TABLE_NAME

#: Mirrors `resume_agent.handler._TARGET_TITLE_CHARS` — kept in sync by the test, not by hope.
TARGET_TITLE_CHARS = 120


def target_title(target_text: str) -> str:
    """First non-empty line of the target, bounded — same rule as the handler's `_target_title`."""
    for line in (target_text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:TARGET_TITLE_CHARS]
    return "Untitled target"


def record_from_trace(trace: dict) -> dict | None:
    """Map a completed RESUMERUN# trace onto its RESUME# record, or ``None`` if it is not eligible.

    Ineligible means: not completed, or missing the S3 keys. A record whose View and Download both
    404 is worse than no record — the list would advertise a résumé that cannot be opened.
    """
    # DynamoDB hands numbers back as `Decimal`, and the write helper marshals through `json.dumps`,
    # which cannot serialise one. The Lambda never hits this because its items are built from
    # Pydantic floats — but anything that reads the table before writing to it must invert first.
    trace = from_ddb_numbers(trace)

    if trace.get("status") != "completed":
        return None
    if not trace.get("html_key") or not trace.get("pdf_key"):
        return None

    run_id = trace.get("run_id") or trace["SK"].split("#", 1)[1]
    target_text = trace.get("target_text") or ""

    record = {
        "PK": trace["PK"],
        "SK": f"RESUME#{run_id}",
        "entity_type": "RESUME",
        "run_id": run_id,
        "status": "completed",
        "created_at": trace.get("created_at"),
        "target_text": target_text,
        "target_title": target_title(target_text),
        "entry_count": len(trace.get("retrieved_ids") or []),
        "html_key": trace["html_key"],
        "pdf_key": trace["pdf_key"],
        "document": trace.get("document"),
        "critique_verdict": trace.get("critique_verdict"),
        "cumulative_tokens": trace.get("cumulative_tokens"),
        "cumulative_cost_usd": trace.get("cumulative_cost_usd"),
        # No `elapsed_seconds` — see the module docstring. No `expires_at` — that is the point.
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--user", required=True, help="Cognito sub of the user to backfill")
    parser.add_argument("--apply", action="store_true", help="Actually write (default: dry run)")
    args = parser.parse_args()

    table = boto3.resource("dynamodb").Table(TABLE_NAME)
    # Paginated deliberately. A RESUMERUN# item carries the full trace list, the document and up to
    # 4,000 chars of target text — tens of KB each — so a heavy user crosses DynamoDB's 1 MB query
    # page well inside a normal history. A single unpaged query would silently migrate the first
    # page, print a confident total and exit 0, and the remainder would be unrecoverable once the
    # traces' own TTL fired. That deadline is exactly what this script races.
    traces: list[dict] = []
    query_kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"USER#{args.user}") & Key("SK").begins_with("RESUMERUN#")
    }
    while True:
        page = table.query(**query_kwargs)
        traces.extend(page.get("Items", []))
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            break
        query_kwargs["ExclusiveStartKey"] = last_key

    print(f"table={TABLE_NAME} user={args.user}")
    print(f"found {len(traces)} RESUMERUN# traces\n")

    written = skipped = existing = 0
    for trace in sorted(traces, key=lambda t: t["SK"]):
        record = record_from_trace(trace)
        if record is None:
            print(f"  skip    {trace['SK']}  (status={trace.get('status')!r}, no artifacts)")
            skipped += 1
            continue

        label = f"{record['run_id']}  {record.get('created_at')}  {record['entry_count']} entries  {record['target_title'][:48]!r}"
        if not args.apply:
            print(f"  WOULD   {label}")
            written += 1
            continue

        try:
            create_resume_record(record)
            print(f"  wrote   {label}")
            written += 1
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                print(f"  exists  {label}")
                existing += 1
            else:
                raise

    verb = "would write" if not args.apply else "wrote"
    print(f"\n{verb} {written} · already present {existing} · skipped {skipped}")
    if not args.apply:
        print("\nDry run. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
