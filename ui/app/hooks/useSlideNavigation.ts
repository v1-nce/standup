"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const GESTURE_MS = 250;
const MIN_DELTA = 8;

export function useSlideNavigation(count: number) {
  const [active, setActive] = useState(0);
  const lastStep = useRef(0);
  const strip = useRef<HTMLDivElement>(null);

  const step = useCallback(
    (delta: number) => setActive((index) => Math.min(count - 1, Math.max(0, index + delta))),
    [count],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest("input, textarea")) return;
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === "ArrowRight") step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  const onWheel = useCallback(
    (event: React.WheelEvent) => {
      const { deltaX, deltaY, timeStamp } = event;
      const delta = Math.abs(deltaX) > Math.abs(deltaY) ? deltaX : deltaY;
      if (Math.abs(delta) < MIN_DELTA || timeStamp - lastStep.current < GESTURE_MS) return;
      lastStep.current = timeStamp;
      step(delta > 0 ? 1 : -1);
    },
    [step],
  );

  useEffect(() => {
    const list = strip.current;
    if (!list?.contains(document.activeElement)) return;
    const thumb = list.children[active];
    if (thumb instanceof HTMLElement) thumb.focus();
  }, [active]);

  return { active, setActive, onWheel, strip };
}
