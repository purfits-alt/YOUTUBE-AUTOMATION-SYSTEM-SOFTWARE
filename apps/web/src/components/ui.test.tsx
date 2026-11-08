import { describe, expect, it } from "vitest";
import { toneFor } from "./ui";

describe("toneFor", () => {
  it("treats high confidence as good and high risk as bad", () => {
    expect(toneFor("High", "confidence")).toBe("ok");
    expect(toneFor("Low", "confidence")).toBe("danger");
    expect(toneFor("High", "inauthenticRisk")).toBe("danger");
    expect(toneFor("Low", "inauthenticRisk")).toBe("ok");
  });
  it("maps common statuses", () => {
    expect(toneFor("Passed")).toBe("ok");
    expect(toneFor("Missing")).toBe("danger");
    expect(toneFor("Expires in 20 h")).toBe("warn");
    expect(toneFor("Script")).toBe("neutral");
  });
});
