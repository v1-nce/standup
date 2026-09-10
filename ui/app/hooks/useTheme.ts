"use client";

import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const getSnapshot = () => document.documentElement.classList.contains("dark");

const getServerSnapshot = () => false;

const emit = () => {
  for (const listener of listeners) listener();
};

/** The app's single theme source of truth: the `dark` class on `<html>`. */
export function useTheme() {
  const dark = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const toggle = () => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("standup-theme", next ? "dark" : "light");
    } catch {
      /* storage unavailable */
    }
    emit();
  };

  return { dark, toggle };
}
