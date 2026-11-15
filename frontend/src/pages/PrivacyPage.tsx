// frontend/src/pages/PrivacyPage.tsx
import { Link } from "react-router";

/** Kept in step with the backend's PRIVACY_POLICY_VERSION; consent records this version. */
export const PRIVACY_POLICY_VERSION = "2026-11";

/**
 * The privacy notice in plain language (UK GDPR, ICO Age Appropriate Design
 * Code). Public: guardians read it before agreeing.
 */
export function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl space-y-4 bg-slate-50 p-4 text-slate-800">
      <h1 className="text-2xl font-bold text-slate-900">Privacy notice</h1>
      <p className="text-sm text-slate-600">Version {PRIVACY_POLICY_VERSION}</p>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">What GCSE Coach is</h2>
        <p>
          A revision app for one student, run privately by their family. It isn&apos;t a school
          service and doesn&apos;t sell or share anyone&apos;s information.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">What we keep, and why</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            The student&apos;s first name or nickname and a username. No email, school or date of
            birth.
          </li>
          <li>Their subjects, exam boards, tiers and set texts, to choose the right questions.</li>
          <li>Their answers, mistakes, progress, points and badges, to help them revise.</li>
          <li>Messages to the tutor about a question, so the conversation can continue.</li>
          <li>Sign-in records, with internet addresses scrambled, to keep the account safe.</li>
        </ul>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">AI and what it sees</h2>
        <p>
          Questions, marking, explanations and the tutor use Claude, an AI from Anthropic. Claude is
          sent the question and the student&apos;s answer or message only, never their name,
          username or any other personal details. Anthropic doesn&apos;t use this to train its AI.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">Who can see it</h2>
        <p>
          The student, the parent or guardian linked to them (a weekly summary), and the person who
          runs the app (to fix problems). Nobody else. There are no adverts, no tracking and no
          public leaderboards.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">How long we keep it</h2>
        <p>
          Until the account is deleted. Technical logs are kept for 30 days. Backups are kept for 30
          days and then deleted.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">Your choices</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Download everything we hold, from the guardian page.</li>
          <li>Withdraw consent at any time, from the guardian page.</li>
          <li>Delete the account and all its data permanently, from the guardian page.</li>
        </ul>
      </section>
      <Link to="/login" className="inline-flex min-h-11 items-center text-brand-700 underline">
        ‹ Back to sign in
      </Link>
    </main>
  );
}
