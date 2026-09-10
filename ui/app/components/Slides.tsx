"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { Deck } from "@/app/api/client";
import { SlideFace } from "@/app/components/SlideFace";
import { useSlideNavigation } from "@/app/hooks/useSlideNavigation";

const FACE = 768;
const FACE_H = (FACE * 9) / 16;
const THUMB = 96;
const MAX_SCALE = 896 / FACE;

export function Slides({ deck }: { deck: Deck | null }) {
  const slides = deck?.slides ?? [];
  const { active, onWheel, setActive, strip } = useSlideNavigation(slides.length);
  const showing = slides[active];

  const stage = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    const el = stage.current;
    if (!el) return;

    const cs = getComputedStyle(el);
    const padX = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
    const padY = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
    const fit = () => {
      const w = el.clientWidth - padX;
      const h = el.clientHeight - padY;
      const s = Math.min(MAX_SCALE, w / FACE, h / FACE_H);
      setScale(s > 0 && s <= MAX_SCALE ? s : 1);
    };

    fit();
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(fit);
      observer.observe(el);
      return () => observer.disconnect();
    }
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);

  const width = FACE * scale;
  const height = FACE_H * scale;

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 p-4" onWheel={onWheel}>
      <div
        ref={stage}
        className="flex min-h-0 flex-1 items-center justify-center overflow-hidden border border-ink p-4"
      >
        <div className="relative" style={{ width, height }}>
          <div
            key={showing?.candidate_id ?? "empty"}
            className="rise absolute top-0 left-0 origin-top-left"
            style={{ width: FACE, height: FACE_H, scale }}
          >
            {showing && deck ? (
              <SlideFace
                design={deck.design}
                label={
                  `Slide ${active + 1} / ${slides.length}` + (showing.free ? " · custom" : "")
                }
                slide={showing}
              />
            ) : (
              <div className="flex h-full w-full flex-col justify-between p-6 sm:p-10">
                <span className="stamp">No deck yet</span>
                <div>
                  <h2 className="font-sans text-3xl font-black tracking-tight uppercase text-balance sm:text-5xl">
                    Ask for one in the chat
                  </h2>
                  <p className="mt-4 max-w-md font-mono text-sm leading-relaxed text-ink-soft">
                    Standup reads the repository and decides what belongs on it.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div ref={strip} className="scroll-thin flex shrink-0 gap-3 overflow-x-auto pb-2">
        {slides.map((slide, index) => (
          <button
            key={slide.candidate_id}
            aria-current={index === active}
            aria-label={`Slide ${index + 1}: ${slide.title}`}
            className={`relative aspect-video shrink-0 overflow-hidden border transition-[box-shadow,opacity,border-color] duration-150 ease-[cubic-bezier(0.25,1,0.5,1)] ${
              index === active
                ? "border-ink shadow-hard"
                : "border-ink-faint opacity-55 hover:opacity-100 hover:shadow-hard"
            }`}
            onClick={() => setActive(index)}
            style={{ width: THUMB }}
            tabIndex={index === active ? 0 : -1}
          >
            <div
              aria-hidden
              className="absolute top-0 left-0 origin-top-left"
              style={{ scale: THUMB / FACE, width: FACE }}
            >
              <SlideFace
                design={deck!.design}
                label={`Slide ${index + 1} / ${slides.length}` + (slide.free ? " · custom" : "")}
                slide={slide}
              />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
