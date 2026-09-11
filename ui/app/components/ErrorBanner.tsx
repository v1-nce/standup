/** A failure surfaced to the user, announced to assistive tech as it appears. */
export function ErrorBanner({ message }: { message: string }) {
  return (
    <p className="stamp-ink shrink-0 px-3 py-2 font-mono text-xs" role="alert">
      {message}
    </p>
  );
}
