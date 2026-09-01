"use client";

import type { Deck } from "@/app/api/client";
import { SlideFace } from "@/app/components/SlideFace";
import { useSlideNavigation } from "@/app/hooks/useSlideNavigation";

const FACE = 768;
const THUMB = 96;

export function Slides({ deck }: { deck: Deck | null }) {
  const slides = deck?.slides ?? [];
  const { active, onWheel, setActive, strip } = useSlideNavigation(slides.length);
  const showing = slides[active];

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-3" onWheel={onWheel}>
      <div className="flex min-h-0 flex-1 items-center justify-center overscroll-contain border border-rule p-4">
        <div key={showing?.candidate_id ?? "empty"} className="rise w-full max-w-3xl">
          {showing && deck ? (
            <SlideFace
              design={deck.design}
              label={`Slide ${active + 1} / ${slides.length}` + (showing.free ? " · custom" : "")}
              slide={showing}
            />
          ) : (
            <article className="flex aspect-video w-full flex-col justify-between border border-rule bg-surface p-6 sm:p-10">
              <span className="label">No deck yet</span>
              <h2 className="text-2xl leading-tight font-semibold text-balance sm:text-4xl">
                Ask for one in the chat
              </h2>
            </article>
          )}
        </div>
      </div>

      <div ref={strip} className="scroll-thin flex shrink-0 gap-2 overflow-x-auto pb-2">
        {slides.map((slide, index) => (
          <button
            key={slide.candidate_id}
            aria-current={index === active}
            aria-label={`Slide ${index + 1}: ${slide.title}`}
            className={`relative aspect-video shrink-0 overflow-hidden border transition-colors focus-visible:outline-none ${
              index === active ? "border-accent" : "border-rule hover:border-muted"
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
