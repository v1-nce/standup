const STEPS = [
  { name: "Index", detail: "symbols · graph · git history · docs", model: false },
  { name: "Gather", detail: "your sentence becomes a window and a filter", model: true },
  { name: "Select", detail: "five signals, weighted, then cut to budget", model: false },
  { name: "Present", detail: "slide text, validated against the index", model: true },
];

export default function Home() {
  return (
    <main className="relative flex flex-1 flex-col">
      <div className="halftone pointer-events-none absolute inset-0" aria-hidden />

      <div className="relative mx-auto flex w-full max-w-3xl flex-1 flex-col gap-14 px-6 py-20">
        <header className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <span className="stamp">STANDUP</span>
            <span className="label">local · nothing uploaded</span>
          </div>

          <h1 className="max-w-xl text-5xl leading-[1.05] font-semibold tracking-tight text-balance">
            Whatever you need to present,{" "}
            <span className="text-accent">as a slide deck.</span>
          </h1>

          <p className="max-w-lg text-lg leading-relaxed text-muted">
            The expensive part isn&apos;t making slides. It&apos;s deciding what to say — so that
            is the part Standup does.
          </p>
        </header>

        <section className="flex flex-col">
          <div className="flex items-baseline justify-between border-b border-rule pb-2">
            <span className="label">The pipeline</span>
            <span className="label">2 model calls per deck</span>
          </div>

          {STEPS.map((step) => (
            <div key={step.name} className="flex items-baseline gap-4 border-b border-rule py-3">
              <span className="figure w-20 text-sm font-medium">{step.name}</span>
              <span className="flex-1 text-sm text-muted">{step.detail}</span>
              <span className="figure text-xs text-muted">
                {step.model ? <span className="text-accent">1 call</span> : "free"}
              </span>
            </div>
          ))}
        </section>

        <section className="flex flex-col gap-3">
          <span className="label">Selection is the product</span>
          <div className="flex flex-wrap items-center gap-1.5" aria-hidden>
            {Array.from({ length: 40 }, (_, index) => (
              <span key={index} className={`pip ${index < 3 ? "pip-on" : ""}`} />
            ))}
          </div>
          <p className="figure text-xs text-muted">
            <span className="text-accent">3 chosen</span> · 37 cut, ranked, and visible before
            anything renders
          </p>
        </section>

        <footer className="mt-auto flex items-center justify-between gap-4 border-t border-rule pt-4">
          <span className="label">Composer not yet wired — drive it over the API</span>
          <span className="label">API.md</span>
        </footer>
      </div>
    </main>
  );
}
