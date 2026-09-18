import { describe, expect, it } from "vitest";
import { normaliseLatex } from "@/lib/math";

describe("normaliseLatex", () => {
  it("repairs legacy escaped square-root commands", () => {
    expect(normaliseLatex("\u0007sqrt{x}")).toBe("\\sqrt{x}");
  });

  it("collapses doubled backslashes", () => {
    expect(normaliseLatex("\\\\frac{1}{2}")).toBe("\\frac{1}{2}");
  });

  it("removes NUL sentinels and repairs a decoded binomial command", () => {
    expect(normaliseLatex("\\u0000\\(S\\u0000\\text{ value}\\)"))
      .toBe("\\(S\\text{ value}\\)");
    expect(normaliseLatex("\u0008inom{8}{4}")).toBe("\\binom{8}{4}");
  });

  it("restores other control-prefixed LaTex commands", () => {
    expect(normaliseLatex("\u000bcdots \u0001alpha \u001cpi"))
      .toBe("\\cdots \\alpha \\pi");
  });
});
