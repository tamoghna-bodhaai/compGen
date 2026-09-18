import { describe, expect, it } from "vitest";
import { normaliseLatex } from "@/lib/math";

describe("normaliseLatex", () => {
  it("repairs legacy escaped square-root commands", () => {
    expect(normaliseLatex("\u0007sqrt{x}")).toBe("\\sqrt{x}");
  });

  it("collapses doubled backslashes", () => {
    expect(normaliseLatex("\\\\frac{1}{2}")).toBe("\\frac{1}{2}");
  });
});
