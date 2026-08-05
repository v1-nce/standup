"use client";

import type { Deck } from "@/app/api/client";
import { useSlideNavigation } from "@/app/hooks/useSlideNavigation";

export function Slides({ deck }: { deck: Deck | null }) {
  const slides = deck?.slides ?? [];
  const { active, onWheel, setActive, strip } = useSlideNavigation(slides.length);
  const showing = slides[active];

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3">
      <div
        className="flex min-h-0 flex-1 items-center justify-center overscroll-contain border border-rule p-4"
        onWheel={onWheel}
      >
        <article
          key={showing?.candidate_id ?? "empty"}
          className="rise flex aspect-video w-full max-w-3xl flex-col justify-between border border-rule bg-surface p-6 sm:p-10"
        >
          <span className="label">
            {showing ? `Slide ${active + 1} / ${slides.length}` : "No deck yet"}
          </span>
          <h2 className="text-2xl leading-tight font-semibold text-balance sm:text-4xl">
            {showing?.title ?? "Ask for one in the chat"}
          </h2>
          <ul className="flex flex-col gap-1 text-sm text-muted sm:text-base">
            {showing?.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}
          </ul>
        </article>
      </div>

      <div ref={strip} className="scroll-thin flex shrink-0 gap-2 overflow-x-auto pb-2">
        {slides.map((slide, index) => (
          <button
            key={slide.candidate_id}
            aria-current={index === active}
            aria-label={`Slide ${index + 1}: ${slide.title}`}
            className={`aspect-video w-24 shrink-0 border p-1.5 text-left transition-colors focus-visible:outline-none sm:w-28 ${
              index === active
                ? "border-accent bg-surface"
                : "border-rule text-muted hover:border-muted"
            }`}
            onClick={() => setActive(index)}
            tabIndex={index === active ? 0 : -1}
          >
            <span className="figure text-[0.625rem]">{index + 1}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
