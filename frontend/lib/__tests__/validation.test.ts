import { describe, expect, it } from "vitest";
import {
  normalizeEmail,
  normalizeLearningGoal,
  normalizeLessonDuration,
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

describe("normalizeLessonDuration", () => {
  it("parses a positive integer", () => {
    expect(normalizeLessonDuration(" 30 ")).toBe(30);
  });
  it("rejects zero", () => {
    expect(normalizeLessonDuration("0")).toBeNull();
  });
  it("rejects non-numeric input", () => {
    expect(normalizeLessonDuration("abc")).toBeNull();
  });
  it("rejects decimals", () => {
    expect(normalizeLessonDuration("30.5")).toBeNull();
  });
});
