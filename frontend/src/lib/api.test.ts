import { afterEach, describe, expect, it, vi } from "vitest";

import { getResumeRun } from "./api";
import { stubFetch } from "../test/http";

/**
 * The poll's status mapping, tested without a component or a timer in sight.
 *
 * `Resume.tsx` polls every 3 seconds, which makes any component-level test of *which* status
 * arrived a race against the queue position of a `fetch` stub. The mapping itself is a pure
 * function of one response body, so it belongs here where it can be asserted exactly once and
 * deterministically.
 */

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("getResumeRun status mapping", () => {
  it("maps draft_ready to a non-terminal draftReady carrying the document (ADR-037 amendment)", async () => {
    stubFetch({
      status: 200,
      body: { status: "draft_ready", run_id: "01JR", document: { summary: "Interim." } },
    });

    const result = await getResumeRun("tok", "01JR");

    expect(result.status).toBe("draftReady");
    // The document rides along; the artifacts do not, because at this point they do not exist.
    expect(result).toMatchObject({ document: { summary: "Interim." } });
    expect(result).not.toHaveProperty("htmlUrl");
    expect(result).not.toHaveProperty("pdfUrl");
  });

  it("still maps failed to failed, so a draft is never a promise of success", async () => {
    stubFetch({ status: 200, body: { status: "failed", run_id: "01JR", message: "Ran out of budget." } });

    const result = await getResumeRun("tok", "01JR");

    expect(result).toMatchObject({ status: "failed", message: "Ran out of budget." });
  });

  it("treats an unrecognised status as pending rather than inventing a terminal one", async () => {
    // Forward compatibility: a future backend state must leave the client polling, not make it
    // declare a run finished. `pending` is the only safe default.
    stubFetch({ status: 200, body: { status: "some_future_phase", run_id: "01JR" } });

    expect((await getResumeRun("tok", "01JR")).status).toBe("pending");
  });

  it("maps a 404 to notfound without reading a body", async () => {
    stubFetch({ status: 404 });

    expect(await getResumeRun("tok", "01JR")).toMatchObject({ status: "notfound", runId: "01JR" });
  });
});
