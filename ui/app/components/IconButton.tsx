export function IconButton({
  children,
  className = "",
  label,
  onClick,
  type = "button",
}: {
  children: React.ReactNode;
  className?: string;
  label: string;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button
      aria-label={label}
      className={`grid h-11 w-11 shrink-0 place-items-center rounded-sm text-ink transition-colors hover:bg-ink/5 ${className}`}
      onClick={onClick}
      type={type}
    >
      <svg
        aria-hidden
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        viewBox="0 0 20 20"
      >
        {children}
      </svg>
    </button>
  );
}

export const MenuPath = <path d="M3 6h14M3 10h14M3 14h14" />;
export const PlusPath = <path d="M10 4v12M4 10h12" />;
export const UpPath = <path d="M10 16V5M5 10l5-5 5 5" />;
