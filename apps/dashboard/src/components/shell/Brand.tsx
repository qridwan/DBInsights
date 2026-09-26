export function Brand({ compact = false, onDark = false }: { compact?: boolean; onDark?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-brand-ink shadow-card">
        <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <ellipse cx="12" cy="6" rx="7" ry="3" />
          <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" />
          <path d="M3 19h4l2-3 3 5 2-4 1 2h6" />
        </svg>
      </span>
      {!compact && (
        <span className="leading-tight">
          <span className={`block text-[15px] font-semibold tracking-tight ${onDark ? "text-white" : "text-ink"}`}>DBInsight</span>
          <span className={`block text-[11px] ${onDark ? "text-slate-400" : "text-muted"}`}>Database health from evidence</span>
        </span>
      )}
    </span>
  );
}
