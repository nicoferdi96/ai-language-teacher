import { describe, expect, it } from "vitest";
import { deviceLabel, deviceSummary, resolveDeviceId } from "../devices";

const devices = [{ deviceId: "default" }, { deviceId: "built-in" }, { deviceId: "airpods" }];

describe("resolveDeviceId", () => {
  it("keeps a saved device that is still plugged in", () => {
    expect(resolveDeviceId(devices, "airpods")).toBe("airpods");
  });

  it("falls back to the system default when the saved device is gone", () => {
    expect(resolveDeviceId(devices, "unplugged-headset")).toBe("default");
  });

  it("uses the first device when the browser lists no default", () => {
    expect(resolveDeviceId([{ deviceId: "a" }, { deviceId: "b" }], undefined)).toBe("a");
  });

  it("is empty when there are no devices", () => {
    expect(resolveDeviceId([], "airpods")).toBe("");
  });
});

describe("deviceLabel", () => {
  it("uses the browser's label", () => {
    expect(deviceLabel({ deviceId: "x", label: " AirPods Pro " }, 0, "audioinput")).toBe("AirPods Pro");
  });

  it("names unlabeled devices by kind and position", () => {
    expect(deviceLabel({ deviceId: "x", label: "" }, 1, "audiooutput")).toBe("Speaker 2");
    expect(deviceLabel({ deviceId: "default", label: "" }, 0, "audioinput")).toBe("System default");
  });
});

describe("deviceSummary", () => {
  it("names a headset once when it does both jobs", () => {
    expect(deviceSummary("Default - AirPods Pro", "AirPods Pro")).toBe("AirPods Pro for mic and speakers");
  });

  it("names mic and speakers separately when they differ", () => {
    expect(deviceSummary("MacBook Pro Microphone", "AirPods Pro")).toBe(
      "Mic: MacBook Pro Microphone · Speakers: AirPods Pro",
    );
  });

  it("falls back to defaults before labels are known", () => {
    expect(deviceSummary("", undefined)).toBe("Your default mic and speakers");
  });
});
