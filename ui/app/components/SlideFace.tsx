import type { CSSProperties, ReactNode } from "react";
import type { Deck } from "@/app/api/client";

type Slide = NonNullable<Deck["slides"]>[number];
type Design = Deck["design"];

const palettes = {
  technical: { background: "#f5f7fb", surface: "#ffffff", text: "#10233f", muted: "#607089", accent: "#2878ff", on_accent: "#ffffff" },
  light: { background: "#fcfcfa", surface: "#f1f4f0", text: "#17211b", muted: "#5d6a62", accent: "#16856b", on_accent: "#ffffff" },
  dark: { background: "#0b1020", surface: "#171e32", text: "#f5f7ff", muted: "#a8b1c7", accent: "#7c9cff", on_accent: "#08101f" },
  editorial: { background: "#f4efe7", surface: "#fffdf8", text: "#241c18", muted: "#74665d", accent: "#b54432", on_accent: "#ffffff" },
  bold: { background: "#f5f238", surface: "#ffffff", text: "#111111", muted: "#555555", accent: "#ff4057", on_accent: "#ffffff" },
};

const resolvedLayout = (slide: Slide) => {
  if (slide.layout !== "auto") return slide.layout;
  if (slide.image) return "image";
  if (slide.secondary_bullets.length) return "two_column";
  if (slide.free && !slide.bullets.length) return "cover";
  return slide.bullets.length <= 1 ? "statement" : "content";
};

function BulletList({ bullets, muted }: { bullets: string[]; muted: string }) {
  return (
    <ul className="flex flex-col gap-2 text-sm sm:text-base" style={{ color: muted }}>
      {bullets.map((bullet, index) => (
        <li key={index} className="flex gap-2">
          <span aria-hidden>•</span><span>{bullet}</span>
        </li>
      ))}
    </ul>
  );
}

function Frame({ children, style }: { children: ReactNode; style: CSSProperties }) {
  return <article className="relative aspect-video w-full overflow-hidden border border-rule" style={style}>{children}</article>;
}

const visualColor = (value: string, palette: Record<string, string>) => {
  if (value === "transparent") return "transparent";
  return value.startsWith("#") ? value : palette[value];
};

function CanvasElement({ element, design, palette }: {
  element: Slide["elements"][number];
  design: Design;
  palette: Record<string, string>;
}) {
  if (element.kind === "line") {
    return (
      <svg aria-hidden className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
        <line
          x1={`${element.x}%`}
          y1={`${element.y}%`}
          x2={`${element.x + element.width}%`}
          y2={`${element.y + element.height}%`}
          stroke={visualColor(element.stroke, palette)}
          strokeWidth={element.stroke_width || 1}
        />
      </svg>
    );
  }

  const position: CSSProperties = {
    position: "absolute",
    left: `${element.x}%`,
    top: `${element.y}%`,
    width: `${element.width}%`,
    height: `${element.height}%`,
    transform: `rotate(${element.rotation}deg)`,
  };
  if (element.kind === "text") {
    return (
      <div
        style={{
          ...position,
          color: visualColor(element.color, palette),
          fontFamily: element.font_family ?? design.body_font,
          fontSize: `${element.font_size / 16}rem`,
          fontWeight: element.font_weight === "regular" ? 400 : element.font_weight === "semibold" ? 600 : 700,
          textAlign: element.align,
          display: "flex",
          alignItems: element.valign === "top" ? "flex-start" : element.valign === "middle" ? "center" : "flex-end",
          whiteSpace: "pre-wrap",
          lineHeight: 1.08,
        }}
      >
        {element.text}
      </div>
    );
  }
  if (element.kind === "image") {
    return (
      <div className="flex items-center justify-center overflow-hidden" style={{ ...position, backgroundColor: palette.surface }}>
        <span className="label px-2 text-center" style={{ color: palette.accent }}>{element.image}</span>
      </div>
    );
  }
  const clipPath = element.shape === "triangle"
    ? "polygon(50% 0, 100% 100%, 0 100%)"
    : element.shape === "chevron"
      ? "polygon(25% 0, 100% 0, 75% 50%, 100% 100%, 25% 100%, 0 50%)"
      : undefined;
  return (
    <div
      aria-hidden
      style={{
        ...position,
        backgroundColor: visualColor(element.fill, palette),
        border: element.stroke_width
          ? `${element.stroke_width}px solid ${visualColor(element.stroke, palette)}`
          : undefined,
        borderRadius: element.shape === "ellipse" ? "50%" : element.shape === "rounded" ? "1rem" : undefined,
        clipPath,
      }}
    />
  );
}

/** Semantic browser preview of the same layout and art-direction contract used by the PPTX renderer. */
export function SlideFace({ label, slide, design }: { label: string; slide: Slide; design: Design }) {
  const base = palettes[design.theme];
  const palette = { ...base, accent: design.accent ?? base.accent };
  const layout = resolvedLayout(slide);
  const frame = { backgroundColor: palette.background, color: palette.text, fontFamily: design.body_font };
  const heading = { fontFamily: design.heading_font };

  if (slide.elements.length) {
    return (
      <Frame style={frame}>
        <h2 className="sr-only">{slide.title}</h2>
        {slide.elements.map((element) => (
          <CanvasElement key={element.id} design={design} element={element} palette={palette} />
        ))}
      </Frame>
    );
  }

  if (layout === "section") {
    return (
      <Frame style={{ ...frame, backgroundColor: palette.accent, color: palette.on_accent }}>
        <span className="absolute top-6 left-7 text-4xl font-bold opacity-80 sm:text-6xl">§</span>
        <div className="flex h-full flex-col justify-center px-[22%]">
          <h2 className="text-3xl leading-tight font-bold sm:text-5xl" style={heading}>{slide.title}</h2>
          {slide.subtitle && <p className="mt-5 text-sm opacity-80 sm:text-lg">{slide.subtitle}</p>}
        </div>
      </Frame>
    );
  }

  if (layout === "cover") {
    return (
      <Frame style={frame}>
        <div className="absolute inset-y-0 left-0 w-2" style={{ backgroundColor: palette.accent }} />
        <div className="flex h-full flex-col justify-center px-[9%] pr-[22%]">
          <span className="label mb-5" style={{ color: palette.accent }}>{slide.subtitle || label}</span>
          <h2 className="text-4xl leading-none font-bold text-balance sm:text-6xl" style={heading}>{slide.title}</h2>
          <BulletList bullets={slide.bullets} muted={palette.muted} />
        </div>
        <div className="absolute top-[12%] right-[7%] aspect-square w-[13%] rounded-2xl" style={{ backgroundColor: palette.surface }} />
      </Frame>
    );
  }

  if (layout === "statement") {
    return (
      <Frame style={frame}>
        <div className="absolute top-[10%] bottom-[10%] left-[6%] w-1" style={{ backgroundColor: palette.accent }} />
        <div className="flex h-full flex-col justify-center px-[11%]">
          <span className="label mb-4" style={{ color: palette.accent }}>{slide.subtitle || label}</span>
          <h2 className="max-w-5xl text-3xl leading-tight font-bold text-balance sm:text-5xl" style={heading}>{slide.title}</h2>
          <div className="mt-7"><BulletList bullets={slide.bullets} muted={palette.muted} /></div>
        </div>
      </Frame>
    );
  }

  if (layout === "two_column") {
    const split = slide.secondary_bullets.length ? slide.bullets : slide.bullets.slice(0, Math.ceil(slide.bullets.length / 2));
    const secondary = slide.secondary_bullets.length ? slide.secondary_bullets : slide.bullets.slice(split.length);
    return (
      <Frame style={frame}>
        <header className="px-[6%] pt-[6%]">
          <span className="label" style={{ color: palette.accent }}>{slide.subtitle || label}</span>
          <h2 className="mt-2 text-2xl font-bold sm:text-4xl" style={heading}>{slide.title}</h2>
        </header>
        <div className="grid grid-cols-2 gap-4 px-[6%] pt-[5%]">
          <div className="rounded-xl p-4 sm:p-6" style={{ backgroundColor: palette.surface }}>
            <strong style={{ color: palette.accent }}>What changed</strong>
            <div className="mt-3"><BulletList bullets={split} muted={palette.text} /></div>
          </div>
          <div className="rounded-xl p-4 sm:p-6" style={{ backgroundColor: palette.surface }}>
            <strong style={{ color: palette.accent }}>{slide.secondary_title || "Why it matters"}</strong>
            <div className="mt-3"><BulletList bullets={secondary} muted={palette.text} /></div>
          </div>
        </div>
      </Frame>
    );
  }

  if (layout === "image") {
    return (
      <Frame style={frame}>
        <div className="flex h-full w-1/2 flex-col justify-center p-[6%]">
          <span className="label mb-3" style={{ color: palette.accent }}>{slide.subtitle || label}</span>
          <h2 className="text-2xl leading-tight font-bold sm:text-4xl" style={heading}>{slide.title}</h2>
          <div className="mt-5"><BulletList bullets={slide.bullets} muted={palette.muted} /></div>
        </div>
        <div className="absolute inset-y-0 right-0 flex w-1/2 items-center justify-center" style={{ backgroundColor: palette.surface }}>
          <span className="label text-center" style={{ color: palette.accent }}>Attached visual</span>
        </div>
      </Frame>
    );
  }

  return (
    <Frame style={frame}>
      <header className="px-[6%] pt-[6%]">
        <span className="label" style={{ color: palette.accent }}>{slide.subtitle || label}</span>
        <h2 className="mt-2 max-w-[68%] text-2xl leading-tight font-bold sm:text-4xl" style={heading}>{slide.title}</h2>
      </header>
      <div className="w-[68%] px-[6%] pt-[6%]"><BulletList bullets={slide.bullets} muted={palette.muted} /></div>
      <aside className="absolute top-[10%] right-[5%] flex h-[78%] w-[24%] items-center rounded-xl p-5" style={{ backgroundColor: palette.surface }}>
        <p className="text-lg leading-snug font-semibold sm:text-2xl" style={heading}>{slide.subtitle || slide.bullets[0] || slide.title}</p>
      </aside>
    </Frame>
  );
}
