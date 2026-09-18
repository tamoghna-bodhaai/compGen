import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "@/lib/api";

describe("apiRequest", () => {
  afterEach(() => vi.restoreAllMocks());

  it("preserves FastAPI detail errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Paper is locked" }), { status: 409, headers: { "Content-Type": "application/json" } }));
    await expect(apiRequest("/papers/p")).rejects.toEqual(new ApiError("Paper is locked", 409));
  });

  it("serializes JSON mutation bodies with the API content type", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await apiRequest("/papers", { method: "POST", body: JSON.stringify({ title: "Paper" }) });
    expect(fetchMock).toHaveBeenCalledWith("/api/papers", expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }));
  });
});
