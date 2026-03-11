import React from "react";
import { Metadata } from "next";
import { unstable_noStore as noStore } from "next/cache";
import { Inter } from "next/font/google";
import Link from "next/link";
import LabelOverlay from "./label-overlay";
import { CopyButton, OpenDialogButton, CloseDialogButton } from "./client-islands";
import { submitEcho } from "./actions";
import { formatUiMap, UiEntry } from "@/lib/ui-map";
import "./pinnacle.css";
import "./theme.css";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Pinnacle",
};

const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });

type Props = { searchParams?: { [k: string]: string | string[] | undefined } };

function qp(val: string | string[] | undefined) {
  return Array.isArray(val) ? val[0] : val || "";
}

function matchesQuery(q: string, label: string) {
  if (!q) return true;
  return label.toLowerCase().includes(q.toLowerCase());
}

function tb(id: string, label: string, section: string, extra?: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base = {
    id,
    "data-testid": id,
    "data-label": `${section}: ${label}`,
    "aria-label": `${section}: ${label}`,
  } as const;
  return base as any as Record<string, string>;
}

function ti(id: string, label: string, section: string) {
  return {
    id,
    "data-testid": id,
    "data-label": `${section}: ${label}`,
    "aria-label": `${section}: ${label}`,
  } as const;
}

function makeEntry(id: string, label: string, section: string): UiEntry {
  return {
    id,
    label: `${section}: ${label}`,
    ariaLabel: `${section}: ${label}`,
    testId: id,
    selector: `[data-testid="${id}"]`,
    section,
  };
}

export default async function Page({ searchParams }: Props) {
  const q = qp(searchParams?.q);
  const showLabels = qp(searchParams?.labels) === "1";
  const echoParam = qp(searchParams?.echo);
  let echoed: any = null;
  if (echoParam) {
    try {
      const json = Buffer.from(echoParam, "base64url").toString("utf8");
      echoed = JSON.parse(json);
    } catch {}
  }
  if (q || showLabels) {
    // Make paths with search params dynamic. Default stays static via revalidate.
    noStore();
  }

  // Build content model once; filter by q
  const entries: UiEntry[] = [];
  const inQ = (s: string, l: string) => matchesQuery(q, `${s}: ${l}`);

  // Hero
  const heroVisible = inQ("Hero", "Hero Header") || inQ("Hero", "Subcopy") || inQ("Hero", "Primary CTA") || inQ("Hero", "Secondary CTA");
  if (heroVisible) {
    entries.push(
      makeEntry("hero-title", "Hero Header", "Hero"),
      makeEntry("hero-sub", "Subcopy", "Hero"),
      makeEntry("hero-cta-primary", "Primary CTA", "Hero"),
      makeEntry("hero-cta-secondary", "Secondary CTA", "Hero")
    );
  }

  // Actions
  if (inQ("Actions", "Primary Button") || inQ("Actions", "Secondary Button") || inQ("Actions", "Ghost Button")) {
    entries.push(
      makeEntry("act-primary", "Primary Button", "Actions"),
      makeEntry("act-secondary", "Secondary Button", "Actions"),
      makeEntry("act-ghost", "Ghost Button", "Actions")
    );
  }

  // Inputs
  if (
    inQ("Inputs", "Text") ||
    inQ("Inputs", "Textarea") ||
    inQ("Inputs", "Select") ||
    inQ("Inputs", "Checkbox") ||
    inQ("Inputs", "Switch")
  ) {
    entries.push(
      makeEntry("in-text", "Text", "Inputs"),
      makeEntry("in-textarea", "Textarea", "Inputs"),
      makeEntry("in-select", "Select", "Inputs"),
      makeEntry("in-checkbox", "Checkbox", "Inputs"),
      makeEntry("in-switch", "Switch", "Inputs"),
      makeEntry("in-invalid", "Invalid", "Inputs")
    );
  }

  // Display
  if (
    inQ("Display", "Card") ||
    inQ("Display", "Table") ||
    inQ("Display", "Badges") ||
    inQ("Display", "Progress") ||
    inQ("Display", "Code")
  ) {
    entries.push(
      makeEntry("disp-card", "Card", "Display"),
      makeEntry("disp-table", "Table", "Display"),
      makeEntry("disp-badge-1", "Badge One", "Display"),
      makeEntry("disp-progress", "Progress", "Display"),
      makeEntry("disp-code", "Code", "Display")
    );
  }

  // Overlays
  if (inQ("Overlays", "Open Modal") || inQ("Overlays", "Dialog")) {
    entries.push(makeEntry("ovl-open", "Open Modal", "Overlays"), makeEntry("ovl-dialog", "Dialog", "Overlays"), makeEntry("ovl-close", "Close Modal", "Overlays"));
  }

  // Form
  if (inQ("Form", "Email") || inQ("Form", "Name") || inQ("Form", "Submit")) {
    entries.push(makeEntry("form-email", "Email", "Form"), makeEntry("form-name", "Name", "Form"), makeEntry("form-submit", "Submit", "Form"));
  }

  const uiMapJson = formatUiMap(entries);

  const toolbarBaseUrl = "/pinnacle";
  const nextLabels = showLabels ? undefined : "1";
  const labelsHref = { pathname: "/pinnacle", query: { ...(q ? { q } : {}), ...(nextLabels ? { labels: nextLabels } : {}) } } as const;
  const filterAction = (value: string) => ({ pathname: "/pinnacle", query: { ...(value ? { q: value } : {}), ...(showLabels ? { labels: "1" } : {}) } } as const);

  // Server action handler for copy UI map: not needed; copy is client-only via Clipboard API in a tiny island below

  return (
    <div className={`${inter.variable} cq pinnacle-theme min-h-screen bg-[var(--bg)] text-[var(--text)]`} style={{ fontFamily: "var(--font-inter), system-ui, sans-serif" }}>
      <LabelOverlay enabled={showLabels} />
      <div className="py-5.5 p-stack-lg">
        {/* Toolbar */}
        <div className="cq-tight mb-5.5 flex flex-wrap items-center gap-3.5">
          <Link
            href={labelsHref}
            role="button"
            className="p-btn p-btn--secondary"
            {...tb("toolbar-toggle-labels", "Show Labels", "Toolbar")}
          >
            <span className="mr-2 inline-block align-middle">
              {/* eye icon */}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </span>
            {showLabels ? "Hide Labels" : "Show Labels"}
          </Link>
          <form className="flex items-center gap-3" method="get" action="/pinnacle">
            <input
              type="search"
              placeholder="Filter…"
              defaultValue={q}
              name="q"
              {...ti("toolbar-filter", "Filter", "Toolbar")}
              className="p-input p-focus min-w-[220px] placeholder:text-[var(--muted)]"
              role="searchbox"
            />
            {showLabels && <input type="hidden" name="labels" value="1" />}
            {/* To avoid hydration for navigation, provide an explicit link button computed on server using current q */}
            <button type="submit" {...tb("toolbar-apply-filter", "Apply Filter", "Toolbar")} className="p-btn p-btn--secondary">
              Apply Filter
            </button>
          </form>
        </div>

        {/* Hero */}
        <section aria-label="Hero" className="mb-7 p-stack">
          <h2 className="mb-3 p-h2">Hero</h2>
          {heroVisible && (
            <div className="p-hero p-surface p-5.5 flex flex-col gap-3.5">
              <h1 className="text-3xl font-bold" id="hero-title" data-testid="hero-title" data-label="Hero: Hero Header" aria-label="Hero: Hero Header">
                Pinnacle UI — minimal, fast, premium
              </h1>
              <p id="hero-sub" data-testid="hero-sub" data-label="Hero: Subcopy" aria-label="Hero: Subcopy" className="p-mute">
                A tiny demo showing what&apos;s possible with Next.js RSC, almost no JS, and great UX.
              </p>
              <div className="flex gap-3">
                <Link href="#actions" className="p-btn p-btn--primary" {...tb("hero-cta-primary", "Primary CTA", "Hero")}>
                  Get Started
                </Link>
                <Link href="#display" className="p-btn p-btn--secondary" {...tb("hero-cta-secondary", "Secondary CTA", "Hero")}>
                  Learn More
                </Link>
              </div>
            </div>
          )}
        </section>

        {/* Actions */}
        <section aria-label="Actions" id="actions" className="mb-7 p-stack">
          <h2 className="mb-3 p-h2">Actions</h2>
      <div className="flex flex-wrap gap-3.5">
            {matchesQuery(q, "Actions: Primary Button") && (
        <button className="p-btn p-btn--primary" {...tb("act-primary", "Primary Button", "Actions")}>
                Primary
              </button>
            )}
            {matchesQuery(q, "Actions: Secondary Button") && (
        <button className="p-btn p-btn--secondary" {...tb("act-secondary", "Secondary Button", "Actions")}>
                Secondary
              </button>
            )}
            {matchesQuery(q, "Actions: Ghost Button") && (
        <button className="p-btn p-btn--ghost" {...tb("act-ghost", "Ghost Button", "Actions")}>
                Ghost
              </button>
            )}
          </div>
        </section>

        {/* Inputs */}
        <section aria-label="Inputs" className="mb-7 p-stack">
          <h2 className="mb-3 p-h2">Inputs</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {matchesQuery(q, "Inputs: Text") && (
              <label className="p-surface p-4 flex flex-col gap-2">
                <span className="text-sm">Text</span>
                <input {...ti("in-text", "Text", "Inputs")} role="textbox" className="p-input p-focus" placeholder="Type here" />
                <span className="p-mute text-xs">Helper text</span>
              </label>
            )}
            {matchesQuery(q, "Inputs: Textarea") && (
              <label className="p-surface p-4 flex flex-col gap-2">
                <span className="text-sm">Textarea</span>
                <textarea {...ti("in-textarea", "Textarea", "Inputs")} className="p-input p-focus" rows={3} placeholder="Write…" />
              </label>
            )}
            {matchesQuery(q, "Inputs: Select") && (
              <label className="p-surface p-4 flex flex-col gap-2">
                <span className="text-sm">Select</span>
                <select {...ti("in-select", "Select", "Inputs")} className="p-input p-focus text-[var(--text)]">
                  <option>One</option>
                  <option>Two</option>
                </select>
              </label>
            )}
            {matchesQuery(q, "Inputs: Checkbox") && (
              <label className="p-surface p-4 flex items-center gap-3">
                <input type="checkbox" className="switch-input" {...ti("in-checkbox", "Checkbox", "Inputs")} />
                <span>Checkbox</span>
              </label>
            )}
            {matchesQuery(q, "Inputs: Switch") && (
              <label className="p-surface p-4 flex items-center gap-3">
                <input type="checkbox" className="switch-input" id="in-switch" data-testid="in-switch" data-label="Inputs: Switch" aria-label="Inputs: Switch" />
                <span className="switch" aria-hidden />
                <span>Switch</span>
              </label>
            )}
            {matchesQuery(q, "Inputs: Invalid") && (
              <label className="p-surface p-4 flex flex-col gap-2">
                <span className="text-sm">Invalid (HTML required)</span>
                <input {...ti("in-invalid", "Invalid", "Inputs")} required className="p-input p-focus" placeholder="Required field" />
              </label>
            )}
          </div>
        </section>

        {/* Display */}
        <section aria-label="Display" id="display" className="mb-7 p-stack">
          <h2 className="mb-3 p-h2">Display</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {matchesQuery(q, "Display: Card") && (
              <div className="p-surface p-4" id="disp-card" data-testid="disp-card" data-label="Display: Card" aria-label="Display: Card">
                <div className="font-medium mb-2">Card</div>
                <p className="text-sm p-mute">A simple card with soft borders and subtle shadow.</p>
              </div>
            )}
            {matchesQuery(q, "Display: Table") && (
              <div className="p-surface p-4">
                <table className="p-table text-left" id="disp-table" data-testid="disp-table" data-label="Display: Table" aria-label="Display: Table" role="table">
                  <thead className="p-mute">
                    <tr className="">
                      <th className="py-1">Name</th>
                      <th className="py-1">Role</th>
                      <th className="py-1">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[1, 2, 3, 4, 5].map((i) => (
                      <tr key={`demo-row-${i}`} className="border-t border-[var(--border)]/40">
                        <td className="py-1">Row {i}</td>
                        <td className="py-1">Member</td>
                        <td className="py-1">Active</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {matchesQuery(q, "Display: Badges") && (
      <div className="p-surface p-4 flex flex-wrap gap-2">
                {["New", "Beta", "Pro"].map((b, i) => (
                  <span
                    key={b}
                    id={`disp-badge-${i + 1}`}
                    data-testid={`disp-badge-${i + 1}`}
                    data-label={`Display: Badge ${b}`}
                    aria-label={`Display: Badge ${b}`}
        className="px-2 py-1 border rounded-[var(--radius)] border-[var(--border)] text-[var(--text)] hover:bg-[color-mix(in_oklab,var(--panel-2)_60%,transparent)]"
                    role="status"
                  >
                    {b}
                  </span>
                ))}
              </div>
            )}
            {matchesQuery(q, "Display: Progress") && (
              <div className="p-surface p-4">
                <div className="text-sm mb-2">Progress</div>
                <div id="disp-progress" data-testid="disp-progress" data-label="Display: Progress" aria-label="Display: Progress" role="progressbar" aria-valuenow={66} aria-valuemin={0} aria-valuemax={100} className="p-progress w-full">
                  <div className="bar" style={{ width: "66%" }} />
                </div>
              </div>
            )}
            {matchesQuery(q, "Display: Code") && (
              <div className="p-surface p-4">
                <pre id="disp-code" data-testid="disp-code" data-label="Display: Code" aria-label="Display: Code" className="text-xs overflow-auto leading-relaxed" style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' }}>
{`fetch('/api', { method: 'POST' })\n  .then(r => r.json())\n  .then(console.log)`}
                </pre>
              </div>
            )}
          </div>
        </section>

        {/* Overlays (dialog) */}
  <section aria-label="Overlays" className="mb-7 p-stack">
      <h2 className="mb-3 p-h2">Overlays</h2>
          <div className="flex items-center gap-3">
            {matchesQuery(q, "Overlays: Open Modal") && <OpenDialogButton idAttr="ovl-open" label="Open Modal" />}
            <dialog id="ovl-dialog" data-testid="ovl-dialog" data-label="Overlays: Dialog" aria-label="Overlays: Dialog" className="p-surface p-5.5 text-[var(--text)]">
              <h3 className="text-lg font-semibold mb-2">Modal</h3>
              <p className="mb-4">This is a native dialog element.</p>
              <CloseDialogButton idAttr="ovl-close" label="Close Modal" />
            </dialog>
          </div>
        </section>

        {/* Form with server action */}
        <section aria-label="Form" className="mb-7 p-stack">
          <h2 className="mb-3 p-h2">Form</h2>
          {/* Server action posts and redirects back with echo query param so JSON renders on server */}
      <form action={submitEcho} className="p-surface p-5.5 grid gap-3.5 max-w-xl">
            <label className="grid gap-2">
              <span>Email</span>
        <input type="email" required className="p-input p-focus" {...ti("form-email", "Email", "Form")} placeholder="you@example.com" />
            </label>
            <label className="grid gap-2">
              <span>Name</span>
        <input type="text" required className="p-input p-focus" {...ti("form-name", "Name", "Form")} placeholder="Ada Lovelace" />
            </label>
            <button id="form-submit" data-testid="form-submit" data-label="Form: Submit" aria-label="Form: Submit" className="p-btn p-btn--primary">Submit</button>
            {echoed && (
        <pre className="text-xs break-all whitespace-pre-wrap p-surface p-3" aria-live="polite">{JSON.stringify(echoed, null, 2)}</pre>
            )}
          </form>
        </section>

        {/* Copy UI Map */}
        <section className="mb-14">
          <CopyButton json={uiMapJson} />
        </section>
      </div>
    </div>
  );
}
