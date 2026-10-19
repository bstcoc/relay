import { describe, expect, test } from "bun:test";
import { plain, rank } from "../app/components/palette";

describe("palette ranking", () => {
  test("a label starting with the query comes before a word inside it, then a mere match", () => {
    const query = plain("mig");
    expect(rank({ label: "Migrations" }, query)).toBe(0);
    expect(rank({ label: "New migration" }, query)).toBe(1);
    expect(rank({ label: "ERP → crm", detail: "Remigrated" }, query)).toBe(2);
    expect(rank({ label: "Map" }, query)).toBe(-1);
  });

  test("accents and case do not matter", () => {
    expect(rank({ label: "Réglages" }, plain("REGL"))).toBe(0);
    expect(rank({ label: "Écarts" }, plain("ecarts"))).toBe(0);
  });
});
