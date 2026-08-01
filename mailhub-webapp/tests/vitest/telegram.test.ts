import { describe, expect, it } from "vitest";
import { parseInitDataUser } from "@/hooks/useAuth";

describe("parseInitDataUser", () => {
  it("parses the user field from initData", () => {
    const initData =
      "user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Alice%22%7D&auth_date=1700000000&hash=abc";
    const user = parseInitDataUser(initData);
    expect(user?.id).toBe(42);
    expect(user?.first_name).toBe("Alice");
  });

  it("returns null for empty initData", () => {
    expect(parseInitDataUser("")).toBeNull();
  });

  it("returns null for missing user field", () => {
    expect(parseInitDataUser("auth_date=1&hash=x")).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseInitDataUser("user=notjson&auth_date=1&hash=x")).toBeNull();
  });
});
