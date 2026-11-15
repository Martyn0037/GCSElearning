// frontend/src/components/AppShell.tsx
import type { ReactNode } from "react";
import { useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router";

import type { UserOut } from "../api/generated/model";
import { homePathForRole } from "../auth/roles";
import { useSignOut } from "../auth/useSession";
import { useSoundSetting } from "../game/sound";
import type { IconName } from "./Icon";
import { Icon } from "./Icon";

const STUDENT_TABS: { to: string; label: string; icon: IconName }[] = [
  { to: "/", label: "Home", icon: "home" },
  { to: "/daily", label: "Daily", icon: "bolt" },
  { to: "/mistakes", label: "Mistakes", icon: "target" },
  { to: "/badges", label: "Badges", icon: "trophy" },
];

/**
 * Page frame: a sticky header with the account menu and, for students, a
 * bottom tab bar (thumb-reachable on a phone) for the main sections.
 */
export function AppShell({ user, children }: { user: UserOut; children: ReactNode }) {
  const isStudent = user.role === "student";
  return (
    <div className="min-h-dvh bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-surface-glass backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-2xl items-center justify-between px-4">
          <Link
            to={homePathForRole(user.role)}
            className="flex items-center gap-2 rounded-lg font-bold tracking-tight text-slate-900 focus-visible:outline-2 focus-visible:outline-brand-600"
          >
            <Logo />
            GCSE Coach
          </Link>
          <AccountMenu user={user} />
        </div>
      </header>
      <main
        className={`mx-auto max-w-2xl animate-fade-up px-4 pt-5 ${isStudent ? "pb-28" : "pb-10"}`}
      >
        {children}
      </main>
      {isStudent && <TabBar />}
    </div>
  );
}

/** The app mark: a rounded gradient tile with a spark. */
export function Logo({ className = "size-8" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`grid place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-800 text-white shadow-brand ${className}`}
    >
      <Icon name="sparkles" className="size-[60%]" />
    </span>
  );
}

function TabBar() {
  return (
    <nav
      aria-label="Main"
      className="pb-safe fixed inset-x-0 bottom-0 z-30 border-t border-slate-200/70 bg-surface-glass backdrop-blur-md"
    >
      <ul className="mx-auto grid max-w-2xl grid-cols-4 px-2 pt-1.5">
        {STUDENT_TABS.map((tab) => (
          <li key={tab.to}>
            <NavLink
              to={tab.to}
              end={tab.to === "/"}
              className={({ isActive }) =>
                `flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-xl text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand-600 ${
                  isActive ? "text-brand-ink" : "text-slate-500 hover:text-slate-800"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`grid h-7 w-12 place-items-center rounded-full transition-colors ${isActive ? "bg-brand-50" : ""}`}
                  >
                    <Icon name={tab.icon} className="size-5" />
                  </span>
                  {tab.label}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function AccountMenu({ user }: { user: UserOut }) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const signOut = useSignOut();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

  // Close on a click outside or Escape.
  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleSignOut() {
    setSigningOut(true);
    await signOut();
    void navigate("/login", { replace: true });
  }

  const initial = user.displayName.trim().charAt(0).toUpperCase() || "?";
  const itemClass =
    "flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-left text-sm text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-brand-600";

  return (
    <div ref={wrapper} className="relative">
      <button
        type="button"
        aria-label="Account menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => {
          setOpen((value) => !value);
        }}
        className="grid size-10 place-items-center rounded-full bg-brand-50 font-semibold text-brand-ink ring-1 ring-brand-200 transition hover:ring-brand-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
      >
        {initial}
      </button>
      {open && (
        <div
          id={menuId}
          className="absolute right-0 mt-2 w-64 origin-top-right animate-fade-up rounded-2xl bg-surface p-2 shadow-raised"
        >
          <p className="px-3 pt-2 pb-3 text-sm text-slate-600">
            Signed in as{" "}
            <span className="font-semibold text-slate-900" aria-label="Signed in as">
              {user.displayName}
            </span>
          </p>
          <div className="border-t border-slate-200 pt-1">
            {user.role === "student" && (
              <>
                <SoundSwitch className={itemClass} />
                <Link to="/setup" className={itemClass}>
                  <Icon name="book" />
                  Change my subjects
                </Link>
              </>
            )}
            <Link to="/privacy" className={itemClass}>
              <Icon name="shield" />
              Privacy notice
            </Link>
            <button
              type="button"
              onClick={() => void handleSignOut()}
              disabled={signingOut}
              className={`${itemClass} disabled:opacity-60`}
            >
              <Icon name="logout" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SoundSwitch({ className }: { className: string }) {
  const [on, setOn] = useSoundSetting();
  return (
    <label className={`${className} cursor-pointer justify-between`}>
      <span className="flex items-center gap-3">
        <Icon name={on ? "volume" : "volumeOff"} />
        Sounds
      </span>
      <input
        type="checkbox"
        checked={on}
        onChange={(e) => {
          setOn(e.target.checked);
        }}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className="relative h-6 w-10 rounded-full bg-slate-300 transition-colors peer-checked:bg-brand-600 peer-focus-visible:outline-2 peer-focus-visible:outline-brand-600 after:absolute after:top-0.5 after:left-0.5 after:size-5 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:after:translate-x-4"
      />
    </label>
  );
}
