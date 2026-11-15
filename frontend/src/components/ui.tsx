// frontend/src/components/ui.tsx
/**
 * Shared building blocks, so every screen has the same buttons, cards,
 * headers and loading states. Styling lives here; pages compose these.
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";

import type { IconName } from "./Icon";
import type { ButtonVariant } from "./styles";
import { buttonClass, cardClass } from "./styles";
import { Icon } from "./Icon";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  block?: boolean;
  size?: "md" | "lg";
  icon?: IconName;
};

/** A button. Defaults to ``type="button"`` so it never submits a form by accident. */
export function Button({
  variant = "primary",
  block = false,
  size = "md",
  icon,
  className = "",
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button type={type} className={`${buttonClass(variant, block, size)} ${className}`} {...rest}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

/** A link styled as a button. */
export function ButtonLink({
  to,
  variant = "primary",
  block = false,
  size = "md",
  icon,
  className = "",
  children,
}: {
  to: string;
  variant?: ButtonVariant;
  block?: boolean;
  size?: "md" | "lg";
  icon?: IconName;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={`${buttonClass(variant, block, size)} ${className}`}>
      {icon && <Icon name={icon} />}
      {children}
    </Link>
  );
}

/** A card. ``as="section"`` with ``aria-label`` makes it a named region. */
export function Card({
  children,
  className = "",
  as: Tag = "div",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article" | "li";
  "aria-label"?: string;
}) {
  return (
    <Tag className={`${cardClass} p-4 ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

/** A "‹ Back" link: small, brand-coloured, with a comfortable touch target. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="-ml-2 mb-1 inline-flex min-h-11 items-center gap-1 rounded-lg px-2 text-sm font-medium text-brand-ink hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-brand-600"
    >
      <Icon name="chevronLeft" className="size-4" />
      {children}
    </Link>
  );
}

/**
 * Page title row: optional back link above, title, optional action on the right.
 */
export function PageHeader({
  title,
  back,
  subtitle,
  action,
}: {
  title: ReactNode;
  back?: { to: string; label: string };
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 animate-fade-up">
      {back && <BackLink to={back.to}>{back.label}</BackLink>}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
        </div>
        {action}
      </div>
    </div>
  );
}

/** A small rounded label. */
export function Chip({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "warn" | "good";
}) {
  const tones = {
    neutral: "bg-slate-100 text-slate-700",
    brand: "bg-brand-50 text-brand-ink",
    warn: "bg-amber-100 text-amber-900",
    good: "bg-green-100 text-green-800",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/** A grey placeholder block shown while content loads. */
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div className={`animate-shimmer rounded-lg bg-slate-200 ${className}`} />;
}

/**
 * Loading placeholder for a list of cards. Announced once as "Loading…".
 *
 * Args:
 *   rows: How many placeholder cards to draw.
 *   label: What screen readers hear.
 */
export function LoadingCards({ rows = 3, label = "Loading…" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-busy="true" className="space-y-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={`${cardClass} space-y-3 p-4`} aria-hidden="true">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
        </div>
      ))}
    </div>
  );
}

/** An error the user should see, with an optional retry. */
export function ErrorNotice({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl bg-red-50 p-4 text-red-900">
      <Icon name="x" className="mt-0.5 size-5" />
      <div className="space-y-2">
        <p>{children}</p>
        {onRetry && (
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    </div>
  );
}

/** A friendly empty state. */
export function EmptyState({
  icon,
  title,
  children,
}: {
  icon: IconName;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className={`${cardClass} flex flex-col items-center gap-2 px-6 py-10 text-center`}>
      <span className="grid size-12 place-items-center rounded-full bg-brand-50 text-brand-ink">
        <Icon name={icon} className="size-6" />
      </span>
      <p className="font-semibold text-slate-900">{title}</p>
      {children && <div className="text-sm text-slate-600">{children}</div>}
    </div>
  );
}

/** A section heading inside a page. */
export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mt-8 mb-3 flex items-center justify-between">
      <h2 className="text-lg font-semibold tracking-tight text-slate-900">{children}</h2>
      {action}
    </div>
  );
}
