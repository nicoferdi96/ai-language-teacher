export type DeviceKind = "audioinput" | "audiooutput";

export type DeviceChoices = { audioinput?: string; audiooutput?: string };

const STORAGE_KEY = "lumi.audio-devices";

/** The learner's last mic and speaker picks; empty when storage is blocked or nothing is saved. */
export function loadDeviceChoices(): DeviceChoices {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    return typeof parsed === "object" && parsed !== null ? (parsed as DeviceChoices) : {};
  } catch {
    return {};
  }
}

export function saveDeviceChoice(kind: DeviceKind, deviceId: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...loadDeviceChoices(), [kind]: deviceId }));
  } catch {
    // Private windows can block storage; the pick still applies to this lesson.
  }
}

/** A readable name; browsers hide labels until mic access is granted. */
export function deviceLabel(device: Pick<MediaDeviceInfo, "deviceId" | "label">, index: number, kind: DeviceKind): string {
  const label = device.label.trim();
  if (label) return label;
  if (device.deviceId === "default") return "System default";
  return `${kind === "audioinput" ? "Microphone" : "Speaker"} ${index + 1}`;
}

/** One line naming the picked mic and speakers, e.g. "AirPods Pro for mic and speakers". */
export function deviceSummary(input: string | undefined, output: string | undefined): string {
  const mic = input && shortLabel(input);
  const speakers = output && shortLabel(output);
  if (mic && mic === speakers) return `${mic} for mic and speakers`;
  if (mic && speakers) return `Mic: ${mic} · Speakers: ${speakers}`;
  if (mic) return `Mic: ${mic}`;
  return "Your default mic and speakers";
}

/** Drops Chrome's "Default - " / "Communications - " prefix. */
function shortLabel(label: string): string {
  return label.replace(/^(Default|Communications) - /, "").trim();
}

/** The id to show as selected: the saved pick if it's still plugged in, else the system default. */
export function resolveDeviceId(devices: Pick<MediaDeviceInfo, "deviceId">[], wanted: string | undefined): string {
  if (wanted && devices.some((device) => device.deviceId === wanted)) return wanted;
  return devices.find((device) => device.deviceId === "default")?.deviceId ?? devices[0]?.deviceId ?? "";
}

/** Whether this browser lets a page pick where audio plays (no on Safari and iOS). */
export function supportsOutputSelection(): boolean {
  return typeof HTMLMediaElement !== "undefined" && "setSinkId" in HTMLMediaElement.prototype;
}
