/** The handful of shared pieces every panel is built from. */

import type { ReactNode } from 'react';

export interface PanelProps {
  title: string;
  children: ReactNode;
  onClose?: (() => void) | undefined;
  className?: string | undefined;
  /** Shown to the right of the title - a count, a status, a hint. */
  badge?: string | undefined;
}

export function Panel({
  title,
  children,
  onClose,
  className,
  badge,
}: PanelProps): React.ReactElement {
  return (
    <section
      className={`pointer-events-auto flex flex-col overflow-hidden rounded-2xl bg-slate-900/85 shadow-xl ring-1 ring-white/10 backdrop-blur ${className ?? ''}`}
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-white/10 px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">{title}</h2>
        {badge && <span className="text-[10px] text-slate-500">{badge}</span>}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label={`Close ${title}`}
            className="ml-auto rounded px-1.5 text-slate-500 transition hover:bg-white/10 hover:text-slate-200"
          >
            ×
          </button>
        )}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </section>
  );
}

export interface ButtonProps {
  onClick: () => void;
  children: ReactNode;
  active?: boolean;
  title?: string;
  disabled?: boolean;
  /** Visually de-emphasised, for destructive or secondary actions. */
  tone?: 'default' | 'quiet' | 'danger';
}

export function Button({
  onClick,
  children,
  active = false,
  title,
  disabled = false,
  tone = 'default',
}: ButtonProps): React.ReactElement {
  const palette = active
    ? 'bg-emerald-500/90 text-slate-900 hover:bg-emerald-400'
    : tone === 'danger'
      ? 'bg-rose-500/20 text-rose-200 hover:bg-rose-500/35'
      : tone === 'quiet'
        ? 'text-slate-400 hover:bg-white/10 hover:text-slate-100'
        : 'bg-white/10 text-slate-100 hover:bg-white/20';

  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={`rounded-lg px-2.5 py-1.5 text-xs font-medium tabular-nums transition disabled:cursor-not-allowed disabled:opacity-40 ${palette}`}
    >
      {children}
    </button>
  );
}

export interface MeterProps {
  label: string;
  /** 0-100. */
  value: number;
  /** Tailwind background class for the filled part. */
  colour?: string;
}

export function Meter({ label, value, colour = 'bg-sky-400' }: MeterProps): React.ReactElement {
  const clamped = Math.max(0, Math.min(100, value));
  // Low needs are the interesting ones, so they shout.
  const urgency = clamped < 20 ? 'bg-rose-500' : clamped < 45 ? 'bg-amber-400' : colour;

  return (
    <div className="flex items-center gap-2">
      <span className="w-14 shrink-0 text-[10px] uppercase tracking-wide text-slate-400">
        {label}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${urgency}`} style={{ width: `${clamped}%` }} />
      </div>
      <span className="w-8 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-400">
        {Math.round(clamped)}
      </span>
    </div>
  );
}

export function Row({ label, value }: { label: string; value: ReactNode }): React.ReactElement {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="text-[11px] text-slate-400">{label}</span>
      <span className="text-right font-mono text-[11px] text-slate-200">{value}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }): React.ReactElement {
  return <p className="px-3 py-6 text-center text-[11px] text-slate-500">{children}</p>;
}
