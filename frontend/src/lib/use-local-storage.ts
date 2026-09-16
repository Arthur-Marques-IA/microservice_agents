"use client";

import { useCallback, useSyncExternalStore } from "react";
import { createId } from "@/lib/id";

/**
 * Estado persistido no `localStorage` via `useSyncExternalStore`: sem
 * `setState` dentro de `useEffect`, sem mismatch de hidratação (no servidor
 * vale o `fallback`) e sincronizado entre abas e entre componentes.
 */

const listeners = new Set<() => void>();

function subscribe(callback: () => void) {
  listeners.add(callback);
  window.addEventListener("storage", callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", callback);
  };
}

function notify() {
  for (const listener of listeners) listener();
}

function readItem(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeLocalStorage(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage bloqueado (modo privado etc.) — segue só em memória.
  }
  notify();
}

export function useLocalStorage<T extends string>(key: string, fallback: T): [T, (value: T) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => (readItem(key) as T | null) ?? fallback,
    () => fallback
  );
  const setValue = useCallback((next: T) => writeLocalStorage(key, next), [key]);
  return [value, setValue];
}

const noopSubscribe = () => () => {};

/** `false` no servidor e na hidratação, `true` depois — para APIs só do browser (portal etc.). */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false
  );
}

const USER_ID_KEY = "agent-service:user-id";

function getOrCreateUserId(): string {
  const existing = readItem(USER_ID_KEY);
  if (existing) return existing;
  const created = createId();
  try {
    window.localStorage.setItem(USER_ID_KEY, created);
  } catch {
    // ignore
  }
  return created;
}

/**
 * `user_id` estável deste browser (sem auth no MVP). String vazia no
 * servidor/hidratação — quem consome deve esperar ter um valor.
 */
export function useUserId(): string {
  return useSyncExternalStore(subscribe, getOrCreateUserId, () => "");
}
