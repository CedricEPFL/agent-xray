import type { DashboardData } from "../lib-data";
import type { ReactNode } from "react";
import { ComponentAttribution } from "./ComponentAttribution";
import { LiteratureMode } from "./LiteratureMode";
import { ParetoChart } from "./ParetoChart";
import { VerdictBanner } from "./VerdictBanner";

const NAV = [
  ["verdict", "01", "Verdict"],
  ["pareto", "02", "Pareto view"],
  ["attribution", "03", "Attribution"],
  ["literature", "04", "Literature mode"],
];

export function Dashboard({ results, literature, errors }: DashboardData) {
  const metadata = results?.metadata ?? {};
  const variants = results?.variants ?? {};
  const hasResults = Boolean(results && Object.keys(variants).length);
  const sampleLabel = typeof metadata.completed_sample_size === "number" && typeof metadata.requested_sample_size === "number"
    ? `${metadata.completed_sample_size}/${metadata.requested_sample_size}`
    : `${metadata.sample_size ?? "—"}`;

  return (
    <div className="mx-auto min-h-screen max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8">
      <div className="grid gap-7 lg:grid-cols-[220px_minmax(0,1fr)] xl:gap-12">
        <aside className="lg:sticky lg:top-8 lg:h-[calc(100vh-4rem)]">
          <div className="flex items-center justify-between lg:block">
            <div><p className="font-mono text-xs uppercase tracking-[0.26em] text-cyan">Agent X-Ray</p><p className="mt-2 hidden max-w-40 text-xs leading-5 text-slate-600 lg:block">Workflow component audit and compute-matched evaluation.</p></div>
            <span className="metric rounded-md border border-line px-2 py-1 text-[10px] text-slate-500">PHASE 2</span>
          </div>
          <nav className="mt-5 flex gap-2 overflow-x-auto pb-2 lg:mt-14 lg:block lg:space-y-1" aria-label="Dashboard sections">
            {NAV.map(([anchor, number, label]) => <a key={anchor} href={`#${anchor}`} className="group flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-500 transition hover:bg-white/[0.035] hover:text-white"><span className="metric text-[10px] text-slate-700 group-hover:text-cyan">{number}</span>{label}</a>)}
          </nav>
          <div className="absolute bottom-0 hidden border-t border-line pt-4 text-[10px] leading-5 text-slate-600 lg:block"><span className="block font-mono text-slate-500">RUNTIME READ</span>Refresh to load the newest checkpoint summary.</div>
        </aside>

        <main className="min-w-0">
          {errors.length ? <div className="mb-5 rounded-lg border border-amber-300/20 bg-amber-300/[0.04] px-4 py-3 text-sm text-amber-100/75">{errors.join(" ")} Continue or run the experiment, then refresh.</div> : null}
          {hasResults && results ? <VerdictBanner results={results} /> : <MissingResults />}

          <Section id="pareto" number="02" eyebrow="Efficiency frontier" title="Accuracy against measured cost" description="Each marker is one variant. Vertical whiskers show the 95% Wilson confidence interval; the horizontal axis is logarithmic.">
            {hasResults ? <ParetoChart variants={variants} /> : <PanelSkeleton />}
          </Section>

          <Section id="attribution" number="03" eyebrow="Component ablations" title="Which components earn their share?" description="Accuracy movement after removal is paired with that component’s share of full-workflow inference cost.">
            {hasResults ? <ComponentAttribution variants={variants} /> : <PanelSkeleton />}
          </Section>

          <Section id="literature" number="04" eyebrow="Published context" title="Literature mode" description="Reported numbers are shown as published—not normalized—and paired with audit observations that matter for comparison.">
            <LiteratureMode literature={literature} />
          </Section>

          <footer className="mt-24 flex flex-col gap-3 border-t border-line py-8 text-xs text-slate-600 sm:flex-row sm:items-center sm:justify-between">
            <p>Agent X-Ray — ASL PoC — Cédric [surname omitted], 2026</p>
            <p className="metric">n={sampleLabel} · seed={metadata.seed ?? "—"} · model={metadata.model ?? "pending"}</p>
          </footer>
        </main>
      </div>
    </div>
  );
}

function Section({ id, number, eyebrow, title, description, children }: { id: string; number: string; eyebrow: string; title: string; description: string; children: ReactNode }) {
  return (
    <section id={id} className="section-anchor mt-24">
      <header className="mb-8 grid gap-3 md:grid-cols-[1fr_1fr] md:items-end"><div><p className="font-mono text-[11px] uppercase tracking-[0.2em] text-cyan/80"><span className="mr-3 text-slate-700">{number}</span>{eyebrow}</p><h2 className="mt-3 text-2xl font-semibold tracking-tight text-white md:text-3xl">{title}</h2></div><p className="max-w-xl text-sm leading-6 text-slate-500 md:justify-self-end">{description}</p></header>
      <div className="panel-grid rounded-2xl border border-line bg-panel/75 p-4 shadow-glow sm:p-6 md:p-8">{children}</div>
    </section>
  );
}

function MissingResults() {
  return <section id="verdict" className="section-anchor rounded-2xl border border-dashed border-amber-300/30 bg-amber-300/[0.035] p-8"><div className="h-2 w-28 animate-pulse rounded bg-amber-200/20" /><h1 className="mt-6 text-3xl font-semibold text-white">Run the experiment to populate Agent X-Ray</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">The dashboard reads <span className="font-mono text-slate-300">results/results.json</span> on every request. Start or continue the experiment, then refresh—no dashboard rebuild is needed.</p></section>;
}

function PanelSkeleton() {
  return <div className="space-y-4 py-10"><div className="h-3 w-2/3 animate-pulse rounded bg-slate-800" /><div className="h-3 w-1/2 animate-pulse rounded bg-slate-800" /><div className="h-56 animate-pulse rounded-xl bg-slate-900/80" /></div>;
}
