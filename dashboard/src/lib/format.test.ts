import { describe, expect, test } from "vitest";
import { fmtMarketCapBillion } from "./format";

describe("fmtMarketCapBillion", () => {
  test("returns 억 only when below 1조 (1000 units)", () => {
    expect(fmtMarketCapBillion(350)).toBe("3,500억");
  });

  test("splits into 조 and 억 when at or above 1000 units", () => {
    // 1500 units = 1.5조 = 1조 5,000억
    expect(fmtMarketCapBillion(1500)).toBe("1조 5,000억");
  });

  test("omits the 억 part when it is an exact multiple of 1조", () => {
    expect(fmtMarketCapBillion(2000)).toBe("2조");
  });

  test("handles zero", () => {
    expect(fmtMarketCapBillion(0)).toBe("0억");
  });
});
