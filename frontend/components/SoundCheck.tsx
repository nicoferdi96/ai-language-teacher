"use client";

import { useLocalParticipant, useMediaDeviceSelect, useTrackVolume } from "@livekit/components-react";
import { type CSSProperties, useCallback, useEffect, useId, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  type DeviceChoices,
  type DeviceKind,
  deviceLabel,
  deviceSummary,
  resolveDeviceId,
  saveDeviceChoice,
  supportsOutputSelection,
} from "@/lib/devices";

const HEARD_LEVEL = 0.06;

/** Pre-lesson sound check: pick a mic and speakers, see the mic level, play a test chime. */
export function SoundCheck({
  choices,
  onChange,
}: {
  choices: DeviceChoices;
  onChange: (kind: DeviceKind, deviceId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const { inputs, outputs, refresh } = useAudioDevices();
  const inputId = resolveDeviceId(inputs, choices.audioinput);
  const outputId = resolveDeviceId(outputs, choices.audiooutput);
  const [attempt, setAttempt] = useState(0);
  const { level, heard, blocked } = useMicLevel(open, choices.audioinput, refresh, attempt);
  const panelId = useId();

  const input = inputs.find((device) => device.deviceId === inputId);
  const output = outputs.find((device) => device.deviceId === outputId);
  const summary = deviceSummary(input?.label, output?.label);

  function pick(kind: DeviceKind, deviceId: string) {
    saveDeviceChoice(kind, deviceId);
    onChange(kind, deviceId);
  }

  return (
    <section className="soundcheck" data-open={open}>
      <div className="soundcheck__head">
        <Icon name="headphones" size={22} />
        <span className="soundcheck__text">
          <span className="soundcheck__title">Sound</span>
          <span className="soundcheck__summary">{summary}</span>
        </span>
        <button
          type="button"
          className="btn btn--quiet btn--sm"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Done" : "Check sound"}
        </button>
      </div>
      {open ? (
        <div id={panelId} className="soundcheck__body">
          {blocked ? (
            <div className="soundcheck__alert" role="alert">
              <p>Your browser is blocking the microphone. Allow it from the icon in the address bar, then try again.</p>
              <button type="button" className="btn btn--quiet btn--sm" onClick={() => setAttempt((n) => n + 1)}>
                Try again
              </button>
            </div>
          ) : null}
          <DeviceFields
            inputs={inputs}
            outputs={outputs}
            inputId={inputId}
            outputId={outputId}
            onPick={pick}
            locked={blocked || inputs.length === 0}
            level={level}
            heard={heard}
            testSound={<TestSoundButton sinkId={outputId} />}
          />
        </div>
      ) : null}
    </section>
  );
}

/** In-lesson sound settings: a toggle beside the mute button that swaps devices on the live call. */
export function SoundSettings() {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const { microphoneTrack } = useLocalParticipant();
  const mic = useMediaDeviceSelect({ kind: "audioinput" });
  const speakers = useMediaDeviceSelect({ kind: "audiooutput" });
  const level = useTrackVolume(microphoneTrack?.audioTrack);
  const heard = useHeard(level);

  useEffect(() => {
    if (!open) return;
    wrap.current?.querySelector<HTMLButtonElement>(".picker__button")?.focus();
    const onPointer = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      toggle.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function pick(kind: DeviceKind, deviceId: string) {
    saveDeviceChoice(kind, deviceId);
    const select = kind === "audioinput" ? mic : speakers;
    select.setActiveMediaDevice(deviceId).catch((err) => console.warn(`Couldn't switch ${kind}:`, err));
  }

  return (
    <div className="sound-settings" ref={wrap}>
      <button
        ref={toggle}
        type="button"
        className="btn btn--quiet btn--icon"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label="Microphone and speaker settings"
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="headphones" size={24} />
      </button>
      {open ? (
        <div id={panelId} className="sound-settings__panel" role="group" aria-label="Microphone and speakers">
          <DeviceFields
            inputs={usable(mic.devices)}
            outputs={usable(speakers.devices)}
            inputId={resolveDeviceId(usable(mic.devices), mic.activeDeviceId)}
            outputId={resolveDeviceId(usable(speakers.devices), speakers.activeDeviceId)}
            onPick={pick}
            locked={usable(mic.devices).length === 0}
            level={level}
            heard={heard}
            dropUp
          />
        </div>
      ) : null}
    </div>
  );
}

/** Mic and speaker selects with a live input meter; shared by the sound check and the in-lesson settings. */
function DeviceFields({
  inputs,
  outputs,
  inputId,
  outputId,
  onPick,
  locked,
  level,
  heard,
  testSound,
  dropUp,
}: {
  inputs: MediaDeviceInfo[];
  outputs: MediaDeviceInfo[];
  inputId: string;
  outputId: string;
  onPick: (kind: DeviceKind, deviceId: string) => void;
  /** No mic access yet, so the browser hides the device list. */
  locked: boolean;
  level: number;
  heard: boolean;
  testSound?: React.ReactNode;
  /** Open lists upward, for the in-lesson panel that sits above the call controls. */
  dropUp?: boolean;
}) {
  const [canPickOutput, setCanPickOutput] = useState(true);
  useEffect(() => setCanPickOutput(supportsOutputSelection()), []);

  return (
    <div className="devices">
      <DeviceSelect kind="audioinput" devices={inputs} value={inputId} locked={locked} dropUp={dropUp} onPick={onPick}>
        <span className="level" aria-hidden="true">
          <span className="level__fill" style={{ "--level": Math.min(level * 2.5, 1) } as CSSProperties} />
        </span>
        <span className="devices__hint" data-heard={heard} aria-live="polite">
          {heard ? <Icon name="check" size={16} /> : null}
          {heard ? "I can hear you" : "Say something to test it"}
        </span>
      </DeviceSelect>
      {canPickOutput && (locked || outputs.length > 0) ? (
        <DeviceSelect kind="audiooutput" devices={outputs} value={outputId} locked={locked} dropUp={dropUp} onPick={onPick}>
          {testSound}
        </DeviceSelect>
      ) : (
        <div className="device">
          <span className="device__label">
            <Icon name="volume" size={18} /> Speakers
          </span>
          <p className="devices__hint">
            This browser plays Lumi through your system sound output. To use headphones, connect them and pick them
            in your device&apos;s sound settings.
          </p>
          {testSound}
        </div>
      )}
    </div>
  );
}

/** A listbox in the app's own style; native selects open the OS menu, which looks out of place. */
function DeviceSelect({
  kind,
  devices,
  value,
  locked,
  dropUp,
  onPick,
  children,
}: {
  kind: DeviceKind;
  devices: MediaDeviceInfo[];
  value: string;
  locked: boolean;
  dropUp?: boolean;
  onPick: (kind: DeviceKind, deviceId: string) => void;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrap = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  const mic = kind === "audioinput";
  const selected = Math.max(0, devices.findIndex((device) => device.deviceId === value));
  const empty = locked ? "Allow the microphone to see your devices" : mic ? "No microphone found" : "No speakers found";

  useEffect(() => {
    if (!open) return;
    list.current?.focus();
    const onPointer = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  useEffect(() => {
    if (open) document.getElementById(`${id}-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [open, active, id]);

  function show() {
    if (devices.length === 0) return;
    setActive(selected);
    setOpen(true);
  }

  function close() {
    setOpen(false);
    button.current?.focus();
  }

  function choose(index: number) {
    const device = devices[index];
    if (device && device.deviceId !== value) onPick(kind, device.deviceId);
    close();
  }

  function onListKey(event: React.KeyboardEvent) {
    const last = devices.length - 1;
    const moves: Record<string, number> = {
      ArrowDown: Math.min(active + 1, last),
      ArrowUp: Math.max(active - 1, 0),
      Home: 0,
      End: last,
    };
    if (event.key in moves) {
      event.preventDefault();
      setActive(moves[event.key]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(active);
    } else if (event.key === "Escape") {
      event.stopPropagation(); // close only the list, not the settings panel around it
      close();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div className="device">
      <span id={`${id}-label`} className="device__label">
        <Icon name={mic ? "mic" : "volume"} size={18} /> {mic ? "Microphone" : "Speakers"}
      </span>
      <span className="picker" ref={wrap} data-up={dropUp}>
        <button
          ref={button}
          id={`${id}-button`}
          type="button"
          className="picker__button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-labelledby={`${id}-label ${id}-button`}
          disabled={devices.length === 0}
          onClick={() => (open ? setOpen(false) : show())}
          onKeyDown={(event) => {
            if (["ArrowDown", "ArrowUp"].includes(event.key)) {
              event.preventDefault();
              show();
            }
          }}
        >
          <span className="picker__value">
            {devices.length ? deviceLabel(devices[selected], selected, kind) : empty}
          </span>
          <Icon name="chevron" size={18} className="picker__chevron" />
        </button>
        {open ? (
          <ul
            ref={list}
            id={`${id}-list`}
            className="picker__list"
            role="listbox"
            tabIndex={-1}
            aria-labelledby={`${id}-label`}
            aria-activedescendant={`${id}-${active}`}
            onKeyDown={onListKey}
          >
            {devices.map((device, index) => (
              <li
                key={device.deviceId}
                id={`${id}-${index}`}
                className="picker__option"
                role="option"
                aria-selected={index === selected}
                data-active={index === active}
                onPointerMove={() => setActive(index)}
                onClick={() => choose(index)}
              >
                <span>{deviceLabel(device, index, kind)}</span>
                {index === selected ? <Icon name="check" size={18} className="picker__check" /> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </span>
      {children}
    </div>
  );
}

/** Plays a short two-note chime on the chosen speakers. */
function TestSoundButton({ sinkId }: { sinkId: string }) {
  const [playing, setPlaying] = useState(false);

  async function play() {
    setPlaying(true);
    const context = new AudioContext();
    try {
      const destination = context.createMediaStreamDestination();
      [660, 880].forEach((frequency, index) => {
        const tone = context.createOscillator();
        const gain = context.createGain();
        const at = context.currentTime + index * 0.18;
        tone.frequency.value = frequency;
        gain.gain.setValueAtTime(0, at);
        gain.gain.linearRampToValueAtTime(0.25, at + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, at + 0.5);
        tone.connect(gain).connect(destination);
        tone.start(at);
        tone.stop(at + 0.55);
      });
      const audio = new Audio();
      audio.srcObject = destination.stream;
      if (sinkId && supportsOutputSelection()) await audio.setSinkId(sinkId);
      await audio.play();
      await new Promise((resolve) => setTimeout(resolve, 900));
      audio.pause();
    } catch (err) {
      console.warn("Test sound failed:", err);
    } finally {
      await context.close();
      setPlaying(false);
    }
  }

  return (
    <button type="button" className="btn btn--quiet btn--sm devices__test" onClick={play} disabled={playing}>
      <Icon name="play" size={16} />
      {playing ? "Playing…" : "Play a test sound"}
    </button>
  );
}

/** Mics and speakers the browser lists, refreshed when headphones are plugged in or out. */
function useAudioDevices() {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const refresh = useCallback(() => {
    navigator.mediaDevices
      ?.enumerateDevices()
      .then(setDevices)
      .catch((err) => console.warn("Couldn't list audio devices:", err));
  }, []);

  useEffect(() => {
    refresh();
    navigator.mediaDevices?.addEventListener("devicechange", refresh);
    return () => navigator.mediaDevices?.removeEventListener("devicechange", refresh);
  }, [refresh]);

  return {
    inputs: usable(devices.filter((device) => device.kind === "audioinput")),
    outputs: usable(devices.filter((device) => device.kind === "audiooutput")),
    refresh,
  };
}

/** Opens the chosen mic while the sound check is open and reports its level (0–1). */
function useMicLevel(active: boolean, deviceId: string | undefined, onGranted: () => void, attempt: number) {
  const [level, setLevel] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const heard = useHeard(level, `${active}:${deviceId}`);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    let frame = 0;

    navigator.mediaDevices
      .getUserMedia({ audio: deviceId ? { deviceId: { ideal: deviceId } } : true })
      .then((granted) => {
        if (cancelled) {
          granted.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = granted;
        setBlocked(false);
        onGranted(); // labels only appear once access is granted
        context = new AudioContext();
        const analyser = context.createAnalyser();
        analyser.fftSize = 512;
        context.createMediaStreamSource(granted).connect(analyser);
        const samples = new Float32Array(analyser.fftSize);
        const tick = () => {
          analyser.getFloatTimeDomainData(samples);
          const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
          setLevel((previous) => (Math.abs(previous - rms) > 0.005 ? rms : previous));
          frame = requestAnimationFrame(tick);
        };
        tick();
      })
      .catch((err) => {
        console.warn("Sound check couldn't open the mic:", err);
        if (!cancelled) setBlocked(true);
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
      context?.close().catch(() => {});
      setLevel(0);
    };
  }, [active, deviceId, onGranted, attempt]);

  return { level, heard, blocked };
}

/** Latches true once the level crosses speaking volume; resets when `resetKey` changes. */
function useHeard(level: number, resetKey?: string): boolean {
  const [heard, setHeard] = useState(false);
  useEffect(() => setHeard(false), [resetKey]);
  useEffect(() => {
    if (level > HEARD_LEVEL) setHeard(true);
  }, [level]);
  return heard;
}

/** Drops the blank entries browsers list before mic access is granted. */
function usable(devices: MediaDeviceInfo[]): MediaDeviceInfo[] {
  return devices.filter((device) => device.deviceId !== "");
}
