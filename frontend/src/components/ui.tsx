import React from "react";
import { haptic } from "../telegram";

type Div = React.HTMLAttributes<HTMLDivElement>;

export function cx(...a: Array<string | false | null | undefined>): string {
  return a.filter(Boolean).join(" ");
}

// ── Card ────────────────────────────────────────────────────────────
export function Card({ className, children, ...rest }: Div) {
  return (
    <div
      className={cx(
        "rounded-xl2 bg-card border border-line shadow-soft p-4",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

// ── Button ──────────────────────────────────────────────────────────
type BtnVariant = "primary" | "ghost" | "danger" | "soft";
interface BtnProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant;
  full?: boolean;
  size?: "md" | "sm";
}
export function Button({
  variant = "primary",
  full,
  size = "md",
  className,
  children,
  onClick,
  ...rest
}: BtnProps) {
  const base =
    "inline-flex items-center justify-center gap-2 font-bold tracking-[-.01em] rounded-xl cursor-pointer select-none transition-all duration-200 active:scale-[.97] disabled:opacity-50 disabled:active:scale-100 disabled:cursor-not-allowed";
  const sizes = size === "sm" ? "px-3 py-2 text-[13px] rounded-[11px]" : "px-4 py-3 text-[15px]";
  const variants: Record<BtnVariant, string> = {
    primary: "text-white shadow-[0_10px_24px_rgba(79,70,229,.34)] hover:shadow-[0_14px_30px_rgba(79,70,229,.42)]",
    ghost: "bg-[var(--soft)] text-text border border-line hover:border-primary/40",
    soft: "bg-primary-soft text-primary hover:bg-primary/10",
    danger: "bg-[var(--danger-soft)] text-[var(--danger)] hover:brightness-95",
  };
  const style = variant === "primary" ? { background: "var(--grad)" } : undefined;
  return (
    <button
      className={cx(base, sizes, variants[variant], full && "w-full", className)}
      style={style}
      // Лёгкая вибрация на каждом нажатии — единый тактильный отклик по всему
      // приложению (вне Telegram — безопасный no-op).
      onClick={(e) => {
        haptic("light");
        onClick?.(e);
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

// ── Field / Input / Select / Textarea ───────────────────────────────
export function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[12px] font-bold text-muted mb-1.5 mt-3.5">{children}</label>
  );
}

const fieldCls =
  "w-full px-3.5 py-3 rounded-[14px] text-[15px] bg-[var(--input-bg)] text-text border border-[var(--input-border)] outline-none transition focus:border-primary focus:shadow-[0_0_0_4px_var(--ring)] placeholder:text-muted/70";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(fieldCls, props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(fieldCls, "resize-y min-h-[44px] leading-relaxed", props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(fieldCls, "appearance-none", props.className)} />;
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      {children}
    </div>
  );
}

// ── Badge ───────────────────────────────────────────────────────────
type BadgeColor = "green" | "amber" | "gray" | "red" | "blue";
export function Badge({ color = "gray", children }: { color?: BadgeColor; children: React.ReactNode }) {
  const map: Record<BadgeColor, string> = {
    green: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    amber: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    gray: "bg-slate-500/15 text-slate-600 dark:text-slate-300",
    red: "bg-rose-500/15 text-rose-600 dark:text-rose-400",
    blue: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-extrabold tracking-wide",
        map[color]
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
      {children}
    </span>
  );
}

// ── Segmented control ───────────────────────────────────────────────
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-1 p-1.5 rounded-[14px] bg-[var(--soft)] border border-line/60">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => {
            if (o.value !== value) haptic("light");
            onChange(o.value);
          }}
          className={cx(
            "flex-1 px-3 py-2.5 rounded-[10px] text-[13px] font-bold cursor-pointer transition-all duration-200 active:scale-[.97]",
            value === o.value ? "bg-card text-text shadow-soft" : "text-muted hover:text-text"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ── Chips (multi-select) ────────────────────────────────────────────
export function Chips({
  options,
  selected,
  onToggle,
}: {
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const active = selected.includes(o.value);
        return (
          <button
            key={o.value}
            onClick={() => onToggle(o.value)}
            className={cx(
              "px-3.5 py-2 rounded-full text-[13px] font-bold border cursor-pointer transition-all duration-200 active:scale-95",
              active
                ? "text-white border-transparent shadow-[0_6px_16px_rgba(79,70,229,.32)]"
                : "bg-card text-text border-line hover:border-primary/40"
            )}
            style={active ? { background: "var(--grad)" } : undefined}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Spinner / Empty / Hint / Row ────────────────────────────────────
export function Spinner() {
  return (
    <div className="mx-auto my-5 h-6 w-6 rounded-full border-[2.5px] border-line border-t-primary animate-spin" />
  );
}

// Скелетоны загрузки: показываем «каркас» списка вместо спиннера — ощущается
// быстрее и аккуратнее.
export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("shimmer rounded-lg", className)} />;
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2.5 mt-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-xl2 bg-card border border-line shadow-soft p-4 flex gap-3">
          <Skeleton className="w-12 h-12 shrink-0 rounded-xl" />
          <div className="flex-1 space-y-2 py-0.5">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Swipeable({
  onSwipe,
  children,
  className,
}: {
  onSwipe: (dir: 1 | -1) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const touch = React.useRef<{ x: number; y: number } | null>(null);
  return (
    <div
      className={className}
      // stopPropagation: горизонтальный свайп здесь — это переключение вкладок.
      // Без этого жест «назад» из края экрана (Shell) перехватывал свайп ВПРАВО
      // и переключение работало только в одну сторону (вперёд).
      onTouchStart={(e) => {
        e.stopPropagation();
        const p = e.touches[0];
        touch.current = { x: p.clientX, y: p.clientY };
      }}
      onTouchEnd={(e) => {
        e.stopPropagation();
        const s = touch.current;
        touch.current = null;
        if (!s) return;
        const p = e.changedTouches[0];
        const dx = p.clientX - s.x;
        const dy = p.clientY - s.y;
        if (Math.abs(dx) < 55 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
        onSwipe(dx < 0 ? 1 : -1);
      }}
    >
      {children}
    </div>
  );
}

// Пустое состояние: опциональная иконка в мягком круге и подзаголовок —
// дружелюбнее голой строки текста. Старые вызовы (только children) работают.
export function Empty({
  children,
  icon,
  sub,
}: {
  children: React.ReactNode;
  icon?: React.ReactNode;
  sub?: React.ReactNode;
}) {
  if (!icon && !sub) return <div className="text-center text-muted text-sm py-7">{children}</div>;
  return (
    <div className="text-center py-9 px-4 animate-fade-up">
      {icon && (
        <div className="mx-auto mb-3 w-14 h-14 rounded-2xl bg-primary-soft text-primary flex items-center justify-center">
          {icon}
        </div>
      )}
      <div className="text-[15px] font-extrabold">{children}</div>
      {sub && <div className="text-[13px] text-muted mt-1.5 leading-relaxed max-w-[300px] mx-auto">{sub}</div>}
    </div>
  );
}

export function Hint({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2.5 rounded-[14px] bg-[var(--soft)] border border-line px-3.5 py-2.5 text-[13px] text-muted leading-relaxed">
      {children}
    </div>
  );
}

export function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 py-2.5 text-sm border-t border-[var(--border)] first:border-t-0">
      <span className="text-muted">{label}</span>
      <span className="text-right font-semibold break-words">{value}</span>
    </div>
  );
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mt-1 mx-0.5 mb-2.5">
      <span className="text-[14px] font-extrabold tracking-tight">{children}</span>
      {action}
    </div>
  );
}
