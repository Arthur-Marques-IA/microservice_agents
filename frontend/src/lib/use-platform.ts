"use client";

import { useSyncExternalStore } from "react";

const noopSubscribe = () => () => {};

/** "⌘" no macOS/iOS, "Ctrl" nos demais (e no servidor). */
export function useModifierKeyLabel(): string {
  return useSyncExternalStore(
    noopSubscribe,
    () => (/Mac|iPhone|iPad|iPod/i.test(navigator.userAgent) ? "⌘" : "Ctrl"),
    () => "Ctrl"
  );
}
