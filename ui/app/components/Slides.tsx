"use client";

import { useSlideNavigation } from "@/app/hooks/useSlideNavigation";

export function Slides({ slides }: { slides: string[] }) {
  const { active, setActive, onWheel } = useSlideNavigation(slides.length);

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3">
      <div
        className="flex min-h-0 flex-1 items-center justify-center overscroll-contain border border-rule p-4"
        onWheel={onWheel}
      >
        <article className="flex aspect-video w-full max-w-3xl flex-col justify-between border border-rule bg-surface p-6 sm:p-10">
          <span className="label">
            Slide {active + 1} / {slides.length}
          </span>
          <h2 className="text-2xl leading-tight font-semibold text-balance sm:text-4xl">
            {slides[active]}
          </h2>
          <span className="label">Nothing built yet</span>
        </article>
      </div>

      <div className="flex shrink-0 gap-2 overflow-x-auto pb-1">
        {slides.map((slide, index) => (
          <button
            key={slide}
            aria-current={index === active}
            aria-label={`Slide ${index + 1}: ${slide}`}
            className={`aspect-video w-24 shrink-0 border p-1.5 text-left transition-colors sm:w-28 ${
              index === active
                ? "border-accent bg-surface"
                : "border-rule text-muted hover:border-ink"
            }`}
            onClick={() => setActive(index)}
          >
            <span className="figure text-[0.625rem]">{index + 1}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
