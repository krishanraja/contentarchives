import { describe, expect, it, beforeAll } from "vitest";
import { clientIp, inAppBrowser, lockState, GLOBAL_FAILURES, PER_IP_FAILURES } from "../lib/gate";
import * as gate from "../lib/gate";
import { MAX_AGE, sign, signMe, stale, verify, verifyMe } from "../lib/session";

describe("the family code", () => {
  it("is retired: nothing compares a typed phrase with a shared code any more (Krish, 2026-10-15)", () => {
    expect(Object.keys(gate)).not.toContain("codeMatches");
  });
});

describe("the network a try came from", () => {
  it("is the first address a proxy names, or 'local' when none does", () => {
    expect(clientIp("203.0.113.9, 10.0.0.1")).toBe("203.0.113.9");
    expect(clientIp(null)).toBe("local");
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
  it("lasts a year, and an emailed-code one is signed again once a day old, so a year counts from the last visit", async () => {
    expect(MAX_AGE).toBe(365 * 24 * 3600);
    const s = (await verify(await sign("grandma", "email")))!;
    const now = Math.floor(Date.now() / 1000);
    expect(s.via).toBe("email");
    expect(Math.abs(s.iat - now)).toBeLessThan(5);
    expect(stale({ ...s, iat: now - 3600 }, now)).toBe(false);
    expect(stale({ ...s, iat: now - 25 * 3600 }, now)).toBe(true);
  });
  it("a session from the retired family code keeps the end it was given (the year rule is for new people)", async () => {
    const old = (await verify(await sign("grandma")))!;
    expect(old.via).toBeUndefined();
    expect(stale({ ...old, iat: old.iat - 30 * 86400 })).toBe(false);
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
