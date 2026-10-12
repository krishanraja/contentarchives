import { describe, expect, it, beforeAll } from "vitest";
import { codeMatches, inAppBrowser, lockState, normalise, GLOBAL_FAILURES, PER_IP_FAILURES } from "../lib/gate";
import { sign, signMe, verify, verifyMe } from "../lib/session";

describe("the family code", () => {
  it("ignores case and spaces", () => {
    // a made-up code: the real one lives only in Vercel's environment
    expect(codeMatches(" sunflower ", "SUNFLOWER")).toBe(true);
    expect(codeMatches("Sun flower", "SUNFLOWER")).toBe(true);
  });
  it("refuses anything else, and an empty expected code", () => {
    expect(codeMatches("SUNFLOWE", "SUNFLOWER")).toBe(false);
    expect(codeMatches("", "")).toBe(false);
  });
  it("normalises full-width letters a phone keyboard may produce", () => {
    expect(normalise("ＳＵＮＦＬＯＷＥＲ")).toBe("SUNFLOWER");
  });
});

describe("locking", () => {
  it("locks one network after too many wrong tries", () => {
    expect(lockState(PER_IP_FAILURES - 1, 0)).toBe("ok");
    expect(lockState(PER_IP_FAILURES, 0)).toBe("ip");
  });
  it("locks everyone when the whole internet is guessing", () => {
    expect(lockState(0, GLOBAL_FAILURES)).toBe("global");
  });
});

describe("in-app browsers", () => {
  it("spots WhatsApp, Instagram and Facebook", () => {
    expect(inAppBrowser("Mozilla/5.0 (iPhone) WhatsApp/2.23")).toBe(true);
    expect(inAppBrowser("Mozilla/5.0 Instagram 300.0")).toBe(true);
    expect(inAppBrowser("Mozilla/5.0 [FBAN/FBIOS;FBAV/400]")).toBe(true);
    expect(inAppBrowser("Mozilla/5.0 (iPhone) Version/17.0 Mobile/15E148 Safari/604.1")).toBe(false);
  });
});

describe("the session cookie", () => {
  beforeAll(() => { process.env.SESSION_SECRET = "test-secret-0123456789abcdef"; process.env.SESSION_VERSION = "1"; });
  it("round-trips who is playing", async () => {
    expect((await verify(await sign("grandma")))?.who).toBe("grandma");
  });
  it("refuses a forged cookie", async () => {
    const t = await sign("grandma");
    expect(await verify(t.slice(0, -3) + "abc")).toBeNull();
  });
  it("signs everyone out when SESSION_VERSION changes", async () => {
    const t = await sign("grandma");
    process.env.SESSION_VERSION = "2";
    expect(await verify(t)).toBeNull();
    process.env.SESSION_VERSION = "1";
  });
});

describe("the phone remembers who it belongs to", () => {
  beforeAll(() => { process.env.SESSION_SECRET = "test-secret-0123456789abcdef"; process.env.SESSION_VERSION = "1"; });
  it("round-trips the name", async () => {
    expect(await verifyMe(await signMe("grandma"))).toBe("grandma");
  });
  it("refuses a forged one", async () => {
    const t = await signMe("grandma");
    expect(await verifyMe(t.slice(0, -3) + "abc")).toBeNull();
  });
  it("is not a key: the name alone never passes for a session, nor a session for a name", async () => {
    expect(await verify(await signMe("grandma"))).toBeNull();
    expect(await verifyMe(await sign("grandma"))).toBeNull();
  });
  it("outlives a SESSION_VERSION bump, so signing everyone out does not forget them", async () => {
    const t = await signMe("grandma");
    process.env.SESSION_VERSION = "2";
    expect(await verifyMe(t)).toBe("grandma");
    process.env.SESSION_VERSION = "1";
  });
});
