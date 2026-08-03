import { describe, expect, it } from "vitest";
import { translate } from "@/lib/i18n";
import { sanitizeHtml } from "@/lib/sanitize";
import { avatarColor, formatRelativeTime, initials } from "@/lib/utils";

describe("i18n translate", () => {
  it("returns English by default", () => {
    expect(translate("en", "nav.inbox")).toBe("Inbox");
  });

  it("returns Russian for ru", () => {
    expect(translate("ru", "nav.inbox")).toBe("Входящие");
  });

  it("interpolates variables", () => {
    expect(
      translate("en", "account.unlink_confirm_description", { email: "a@b.c" }),
    ).toContain("a@b.c");
  });

  it("falls back to the key for unknown keys", () => {
    expect(translate("en", "no.such.key")).toBe("no.such.key");
  });
});

describe("avatarColor", () => {
  it("is deterministic for the same seed", () => {
    expect(avatarColor("alice@gmail.com")).toBe(avatarColor("alice@gmail.com"));
  });

  it("returns a valid tailwind class", () => {
    expect(avatarColor("x@y.z")).toMatch(/^bg-(amber|orange|rose|red|pink)-\d+$/);
  });
});

describe("initials", () => {
  it("extracts two initials from a full name", () => {
    expect(initials("John Doe")).toBe("JD");
  });

  it("handles single-word names", () => {
    expect(initials("alice@gmail.com")).toBe("AL");
  });

  it("falls back for empty input", () => {
    expect(initials("")).toBe("?");
  });
});

describe("formatRelativeTime", () => {
  it("formats relative time in English", () => {
    const result = formatRelativeTime(Math.floor(Date.now() / 1000) - 300, "en");
    expect(result).toMatch(/ago/i);
  });

  it("always prefixes relative time with the ~ symbol", () => {
    const en = formatRelativeTime(Math.floor(Date.now() / 1000) - 300, "en");
    expect(en.startsWith("~ ")).toBe(true);
    expect(en).not.toMatch(/^about/i);
    const ru = formatRelativeTime(Math.floor(Date.now() / 1000) - 300, "ru");
    expect(ru.startsWith("~ ")).toBe(true);
    expect(ru).not.toMatch(/^около/i);
  });
});

describe("sanitizeHtml", () => {
  it("strips scripts and event handlers but keeps links", () => {
    const out = sanitizeHtml(
      '<p>Hi <a href="https://x.com" onclick="evil()">link</a></p><script>alert(1)</script><img src="javascript:alert(1)">',
    );
    expect(out).toContain("<a");
    expect(out).toContain("Hi");
    expect(out).not.toContain("script");
    expect(out).not.toContain("onclick");
    expect(out).not.toContain("javascript:");
  });
});
