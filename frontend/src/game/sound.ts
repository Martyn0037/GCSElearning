// frontend/src/game/sound.ts
// Short reward sounds, generated with Web Audio (no audio files). Muted by
// default; the setting lives on this device only.
import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "gcse-coach:sounds";
const listeners = new Set<() => void>();

export type Cue = "correct" | "levelUp" | "badge";

/** Notes (Hz) and length (s) for each cue: short and quiet, never a fanfare. */
const CUES: Record<Cue, { notes: number[]; length: number }> = {
  correct: { notes: [660, 880], length: 0.09 },
  levelUp: { notes: [523, 659, 784, 1047], length: 0.1 },
  badge: { notes: [784, 988, 1175], length: 0.11 },
};

function read(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "on";
  } catch {
    return false; // storage blocked: stay muted
  }
}

/** Turn sounds on or off for this device. */
export function setSoundsOn(on: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
  } catch {
    // Storage blocked: the choice lasts until the page reloads.
  }
  memory = on;
  listeners.forEach((listener) => {
    listener();
  });
}

let memory: boolean | null = null;

/** Whether sounds are on (default: off). */
export function soundsOn(): boolean {
  return memory ?? read();
}

/** React hook for the sound setting. */
export function useSoundSetting(): [boolean, (on: boolean) => void] {
  const subscribe = useCallback((listener: () => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  const on = useSyncExternalStore(subscribe, soundsOn, () => false);
  return [on, setSoundsOn];
}

/** Play a cue if sounds are on and the browser supports Web Audio. Never throws. */
export function playCue(cue: Cue): void {
  if (!soundsOn()) return;
  try {
    const AudioCtx = window.AudioContext as (new () => AudioContext) | undefined;
    if (!AudioCtx) return;
    const context = new AudioCtx();
    const { notes, length } = CUES[cue];
    notes.forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const start = context.currentTime + index * length;
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.08, start);
      gain.gain.exponentialRampToValueAtTime(0.001, start + length);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(start);
      oscillator.stop(start + length);
    });
    window.setTimeout(() => void context.close(), (notes.length + 1) * length * 1000);
  } catch {
    // Audio isn't essential; ignore any failure.
  }
}
