const SURFACES = {
  paper: "bg-paper text-ink enabled:hover:bg-ink enabled:hover:text-paper",
  ink: "bg-ink text-paper enabled:hover:bg-paper enabled:hover:text-ink",
} as const;

export function IconButton({
  children,
  className = "h-11 w-11",
  disabled = false,
  label,
  onClick,
  type = "button",
  variant = "paper",
}: {
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  label: string;
  onClick?: () => void;
  type?: "button" | "submit";
  variant?: keyof typeof SURFACES;
}) {
  return (
    <button
      aria-label={label}
      className={`press grid shrink-0 place-items-center border border-ink shadow-hard disabled:cursor-not-allowed disabled:opacity-40 ${SURFACES[variant]} ${className}`}
      disabled={disabled}
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
export const UpPath = <path d="M10 15V5M5 10l5-5 5 5" />;
export const PencilPath = <path d="M13 4l3 3-9 9H4v-3z" />;
export const TrashPath = <path d="M4 6h12M7.5 6V4h5v2M6 6l.8 10h6.4L15 6M8.5 9v4M11.5 9v4" />;
export const ClosePath = <path d="M5 5l10 10M15 5L5 15" />;
export const MoonPath = <path d="M15.5 12.5A6 6 0 1 1 7.5 4.5a5 5 0 0 0 8 8z" />;
export const SunPath = (
  <>
    <circle cx="10" cy="10" r="3.5" />
    <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4" />
  </>
);
