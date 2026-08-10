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
          <SlideFace
            bullets={showing?.bullets ?? []}
            label={showing ? `Slide ${active + 1} / ${slides.length}` : "No deck yet"}
            title={showing?.title ?? "Ask for one in the chat"}
          />
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
                bullets={slide.bullets}
                label={`Slide ${index + 1} / ${slides.length}`}
                title={slide.title}
              />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
