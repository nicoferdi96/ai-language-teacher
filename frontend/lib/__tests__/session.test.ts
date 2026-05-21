import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = { get: vi.fn(), set: vi.fn() };

vi.mock("next/headers", () => ({
  cookies: async () => cookieStore,
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`REDIRECT:${url}`);
  },
}));

import { setUserEmail, getUserEmail, requireUserEmail } from "../session";

beforeEach(() => {
  cookieStore.get.mockReset();
  cookieStore.set.mockReset();
});

describe("setUserEmail", () => {
  it("writes an httpOnly user_email cookie with a 1-day maxAge", async () => {
    await setUserEmail("a@b.com");
    expect(cookieStore.set).toHaveBeenCalledWith("user_email", "a@b.com", {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24,
    });
  });
});

describe("getUserEmail", () => {
  it("returns the cookie value when present", async () => {
    cookieStore.get.mockReturnValue({ value: "a@b.com" });
    expect(await getUserEmail()).toBe("a@b.com");
  });
  it("returns null when the cookie is missing", async () => {
    cookieStore.get.mockReturnValue(undefined);
    expect(await getUserEmail()).toBeNull();
  });
});

describe("requireUserEmail", () => {
  it("returns the email when the cookie is present", async () => {
    cookieStore.get.mockReturnValue({ value: "a@b.com" });
    await expect(requireUserEmail()).resolves.toBe("a@b.com");
  });
  it("redirects to / when the cookie is missing", async () => {
    cookieStore.get.mockReturnValue(undefined);
    await expect(requireUserEmail()).rejects.toThrow("REDIRECT:/");
  });
});
