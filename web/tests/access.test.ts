import { beforeAll, describe, expect, it } from "vitest";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { cleanCode, codeHash, newCode, normEmail, normName, stepFor } from "../lib/access";
import { askMail, codeMail, send } from "../lib/mail";
import { sign, signAsking, signDecide, signMe, verify, verifyAsking, verifyDecide, verifyMe } from "../lib/session";

// Made-up people only: real addresses live only in the database.
beforeAll(() => { process.env.SESSION_SECRET = "test-secret-0123456789abcdef"; process.env.SESSION_VERSION = "1"; });

describe("an email address", () => {
  it("is the same address whatever its case or the spaces around it", () => {
    expect(normEmail("  Grandma@Family.TEST ")).toBe("grandma@family.test");
  });
  it("is refused when it is not shaped like one", () => {
    for (const bad of ["", "grandma", "grandma@", "@family.test", "grand ma@family.test", "a@b", `${"x".repeat(250)}@family.test`])
      expect(normEmail(bad), bad).toBeNull();
  });
});

describe("a first name", () => {
  it("is tidied like a name on Who are you?, and needs two letters", () => {
    expect(normName("  Cousin   Tara ")).toBe("Cousin Tara");
    expect(normName("T")).toBeNull();
    expect(normName("x".repeat(60))!.length).toBe(40);
  });
});

describe("a code", () => {
  it("is six digits, and typed with spaces, dashes or around words it is the same code", () => {
    expect(newCode()).toMatch(/^\d{6}$/);
    expect(cleanCode("123 456")).toBe("123456");
    expect(cleanCode("Your code is 123-456")).toBe("123456");
    expect(cleanCode("１２３４５６")).toBe("123456");
  });
  it("is not the same code twice in a row, or the same few over many", () => {
    const seen = new Set(Array.from({ length: 200 }, newCode));
    expect(seen.size).toBeGreaterThan(190);
  });
  it("is stored only as a hash keyed by the secret and the address", () => {
    const h = codeHash("s1", "grandma@family.test", "123456");
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    expect(h).not.toContain("123456");
    expect(codeHash("s2", "grandma@family.test", "123456")).not.toBe(h);
    expect(codeHash("s1", "grandpa@family.test", "123456")).not.toBe(h);
  });
});

describe("the step a phone is on", () => {
  it("follows the email typed and what Krish said", () => {
    expect(stepFor(null, null)).toBe("email");
    expect(stepFor("tara@family.test", null)).toBe("name");
    expect(stepFor("tara@family.test", "asked")).toBe("waiting");
    expect(stepFor("tara@family.test", "no")).toBe("no");
    expect(stepFor("tara@family.test", "yes")).toBe("code");
  });
});

describe("each kind of signed token opens only its own door", () => {
  it("the asking cookie a stranger is handed is never a session, a name, or Krish's yes-or-no link", async () => {
    const asking = await signAsking("stranger@family.test");
    expect(await verifyAsking(asking)).toBe("stranger@family.test");
    expect(await verify(asking)).toBeNull();
    expect(await verifyMe(asking)).toBeNull();
    expect(await verifyDecide(asking)).toBeNull();
  });
  it("Krish's link is not a session or an asking cookie, and a session is not his link", async () => {
    const link = await signDecide("tara@family.test");
    expect(await verifyDecide(link)).toBe("tara@family.test");
    expect(await verify(link)).toBeNull();
    expect(await verifyAsking(link)).toBeNull();
    expect(await verifyDecide(await sign("grandma"))).toBeNull();
    expect(await verifyDecide(await signMe("grandma"))).toBeNull();
  });
  it("a forged link is refused", async () => {
    const link = await signDecide("tara@family.test");
    expect(await verifyDecide(link.slice(0, -3) + "abc")).toBeNull();
  });
});

describe("the emails", () => {
  const site = "https://archives.example";
  it("put the code where a phone shows it first: the subject", () => {
    const m = codeMail("tara@family.test", "Cousin Tara", "042917", { minutes: 30, approved: false, site });
    expect(m.subject).toContain("042917");
    expect(m.text).toContain("042917");
    expect(m.text).toContain("30 minutes");
  });
  it("say Krish said yes, and for how long that code works", () => {
    const m = codeMail("tara@family.test", "Cousin Tara", "042917", { minutes: 3 * 24 * 60, approved: true, site });
    expect(m.subject).toMatch(/^Krish said yes!/);
    expect(m.text).toContain("3 days");
    expect(m.text).toContain(site);
  });
  it("never let a typed name write into the page of an email", () => {
    const m = askMail("admin@family.test", "<img src=x onerror=alert(1)>", "x@family.test", `${site}/approve?t=abc`);
    expect(m.html).not.toContain("<img");
    expect(m.html).toContain("&lt;img");
  });
  it("tell Krish that opening the link decides nothing", () => {
    const m = askMail("admin@family.test", "Cousin Tara", "tara@family.test", `${site}/approve?t=abc`);
    expect(m.text).toContain(`${site}/approve?t=abc`);
    expect(m.text).toContain("Nothing happens until you tap a button");
  });
});

describe("the local test mailbox", () => {
  it("writes each email to a file", async () => {
    const f = join(mkdtempSync(join(tmpdir(), "mail-")), "mail.jsonl");
    process.env.MAIL_SINK = f;
    try {
      expect(await send({ to: "tara@family.test", subject: "s", text: "t", html: "h" })).toBe(true);
      expect(JSON.parse(readFileSync(f, "utf8").trim()).to).toBe("tara@family.test");
    } finally { delete process.env.MAIL_SINK; }
  });
  it("is refused on Vercel, so a stray setting can never swallow the family's real emails", async () => {
    process.env.MAIL_SINK = "/tmp/never.jsonl"; process.env.VERCEL = "1";
    try {
      await expect(send({ to: "tara@family.test", subject: "s", text: "t", html: "h" })).rejects.toThrow(/local tests only/);
    } finally { delete process.env.MAIL_SINK; delete process.env.VERCEL; }
  });
});
