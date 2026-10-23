import { describe, expect, it } from "vitest";
import {
  normalizeEmail,
  normalizeLearningGoal,
  normalizeNativeLanguage,
  normalizeTargetLanguage,
} from "../validation";

describe("normalizeEmail", () => {
  it("lowercases and trims a valid email", () => {
    expect(normalizeEmail("  User@Example.COM ")).toBe("user@example.com");
  });
  it("rejects a string without @", () => {
    expect(normalizeEmail("notanemail")).toBeNull();
  });
  it("rejects an empty string", () => {
    expect(normalizeEmail("")).toBeNull();
  });
});

describe("normalizeLearningGoal", () => {
  it("trims a non-empty answer", () => {
    expect(normalizeLearningGoal("  casual chat  ")).toBe("casual chat");
  });
  it("rejects whitespace-only input", () => {
    expect(normalizeLearningGoal("   ")).toBeNull();
  });
});

describe("normalizeTargetLanguage", () => {
  it("accepts the four supported codes", () => {
    expect(["en", "es", "de", "fr"].map(normalizeTargetLanguage)).toEqual(["en", "es", "de", "fr"]);
  });
  it("normalizes case and whitespace", () => {
    expect(normalizeTargetLanguage(" ES ")).toBe("es");
  });
  it("rejects Italian, which Gradium cannot speak", () => {
    expect(normalizeTargetLanguage("it")).toBeNull();
  });
});

describe("normalizeNativeLanguage", () => {
  it("capitalizes a typed language", () => {
    expect(normalizeNativeLanguage("  italian ")).toBe("Italian");
  });
  it("accepts non-Latin scripts", () => {
    expect(normalizeNativeLanguage("Українська")).toBe("Українська");
  });
  it("rejects digits and symbols", () => {
    expect(normalizeNativeLanguage("123")).toBeNull();
    expect(normalizeNativeLanguage("<script>")).toBeNull();
  });
});
