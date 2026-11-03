import { describe, expect, it } from "vitest";
import { dateLabel } from "../src/components/monitoringTypes";

describe("dateLabel uses the application event timezone", () => {
  it.each([
    ["2026-11-03T04:56:06Z", "03/11/2026, 05:56:06"],
    ["2026-11-03T05:00:27Z", "03/11/2026, 06:00:27"],
    ["2026-07-03T04:56:06Z", "03/07/2026, 06:56:06"],
  ])("formats %s in Europe/Madrid as %s", (timestamp, expected) => {
    expect(dateLabel(timestamp)).toBe(expected);
  });
});
