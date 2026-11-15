// frontend/src/components/styles.ts
/** Class-name helpers shared by components (kept apart so React Fast Refresh works). */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success" | "neutral";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-600 text-white shadow-brand hover:bg-brand-700 active:bg-brand-800 disabled:shadow-none",
  secondary:
    "bg-surface text-brand-ink ring-1 ring-inset ring-slate-300 shadow-card hover:bg-brand-50",
  ghost: "text-brand-ink hover:bg-brand-50",
  danger: "bg-red-600 text-white hover:bg-red-700",
  success: "bg-green-700 text-white hover:bg-green-800",
  neutral: "bg-slate-800 text-slate-50 hover:bg-slate-900",
};

/**
 * Classes for a button-looking control.
 *
 * Args:
 *   variant: Visual weight.
 *   block: Full width.
 *   size: ``md`` (44px, the minimum touch target) or ``lg`` (52px, main actions).
 */
export function buttonClass(
  variant: ButtonVariant = "primary",
  block = false,
  size: "md" | "lg" = "md",
) {
  return [
    "inline-flex items-center justify-center gap-2 rounded-xl px-4 text-center font-semibold",
    "transition-[background-color,box-shadow,transform] duration-150 active:scale-[0.98]",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600",
    "disabled:cursor-not-allowed disabled:opacity-55 disabled:active:scale-100",
    size === "lg" ? "min-h-13 text-base" : "min-h-11 text-sm",
    block ? "w-full" : "",
    VARIANTS[variant],
  ].join(" ");
}

/** The standard card surface. */
export const cardClass = "rounded-2xl bg-surface shadow-card";
