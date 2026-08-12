/** The slide itself. Rendered once at full size on the stage, and again scaled down per thumbnail. */
export function SlideFace({
  label,
  title,
  bullets,
}: {
  label: string;
  title: string;
  bullets: string[];
}) {
  return (
    <article className="flex aspect-video w-full flex-col justify-between border border-rule bg-surface p-6 sm:p-10">
      <span className="label">{label}</span>
      <h2 className="text-2xl leading-tight font-semibold text-balance sm:text-4xl">{title}</h2>
      <ul className="flex flex-col gap-1 text-sm text-muted sm:text-base">
        {bullets.map((bullet, index) => (
          <li key={index}>{bullet}</li>
        ))}
      </ul>
    </article>
  );
}
