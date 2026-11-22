export function Logo({ className = "h-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 112 32" className={className} role="img" aria-label="Envo">
      <rect width="32" height="32" rx="8" fill="#18181b" />
      <path
        d="M10 9h12M10 16h9M10 23h12M10 9v14"
        stroke="#fafafa"
        strokeWidth="2.6"
        strokeLinecap="round"
        fill="none"
      />
      <text
        x="42"
        y="23"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        fontSize="20"
        fontWeight="650"
        fill="#18181b"
        letterSpacing="-0.5"
      >
        envo
      </text>
    </svg>
  );
}
