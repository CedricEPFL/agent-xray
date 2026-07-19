import type { DashboardData, ExperimentResults, StudyId } from "../lib-data";
import type { ReactNode } from "react";
import { ComponentAttribution } from "./ComponentAttribution";
import { EscalationStudy } from "./EscalationStudy";
import { LabelAudit } from "./LabelAudit";
import { LiteratureMode } from "./LiteratureMode";
import { ParetoChart } from "./ParetoChart";
import { VerdictBanner } from "./VerdictBanner";
import { finite, usd } from "./format";

const PUBLIC_REPO = "https://github.com/CedricEPFL/agent-xray";

const STUDIES: { id: StudyId; number: string; label: string; short: string }[] = [
  { id: "math500", number: "01", label: "MATH-500 (preregistered)", short: "MATH-500" },
  { id: "gsm8k", number: "02", label: "GSM8K anchor", short: "GSM8K" },
  { id: "escalation", number: "03", label: "Escalation", short: "Escalation" },
  { id: "audit", number: "04", label: "Label audit", short: "Label audit" },
  { id: "literature", number: "05", label: "Literature", short: "Literature" },
];

type DashboardProps = DashboardData & { activeStudy: StudyId };

export function Dashboard(props: DashboardProps) {
  const { activeStudy, errors, spend, modelName } = props;
  const active = STUDIES.find((study) => study.id === activeStudy) ?? STUDIES[0];

  return (
    <div className="mx-auto min-h-screen max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8">
      <div className="grid gap-7 lg:grid-cols-[250px_minmax(0,1fr)] xl:gap-12">
        <aside className="lg:sticky lg:top-8 lg:flex lg:h-[calc(100vh-4rem)] lg:flex-col">
          <div className="flex items-center justify-between lg:block">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.26em] text-cyan">Agent X-Ray</p>
              <p className="mt-2 hidden max-w-48 text-xs leading-5 text-slate-600 lg:block">A preregistered accuracy–cost audit of structure, sampling, and escalation.</p>
            </div>
            <span className="metric rounded-md border border-line px-2 py-1 text-[10px] text-slate-500 lg:mt-5 lg:inline-block">RESEARCH V2</span>
          </div>
          <nav className="mt-5 flex gap-2 overflow-x-auto pb-2 lg:mt-12 lg:block lg:space-y-1" aria-label="Study switcher">
            {STUDIES.map((study) => {
              const selected = study.id === activeStudy;
              return (
                <a
                  key={study.id}
                  href={`?study=${study.id}`}
                  aria-current={selected ? "page" : undefined}
                  className={`group flex shrink-0 items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition ${selected ? "border-cyan/20 bg-cyan/[0.07] text-white" : "border-transparent text-slate-500 hover:bg-white/[0.035] hover:text-white"}`}
                >
                  <span className={`metric text-[10px] ${selected ? "text-cyan" : "text-slate-700 group-hover:text-cyan"}`}>{study.number}</span>
                  <span className="hidden lg:inline">{study.label}</span>
                  <span className="lg:hidden">{study.short}</span>
                </a>
              );
            })}
          </nav>
          <div className="mt-auto hidden border-t border-line pt-4 text-[10px] leading-5 text-slate-600 lg:block">
            <span className="block font-mono text-slate-500">REQUEST-TIME DATA</span>
            Result and audit files are read from disk on every page request.
          </div>
        </aside>

        <main className="min-w-0">
          <header className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-600">Study {active.number} / 05</p>
              <h1 className="mt-2 text-xl font-medium text-white">{active.label}</h1>
            </div>
            <p className="metric text-[10px] uppercase tracking-[0.12em] text-slate-600">live artifact · refresh for latest disk state</p>
          </header>

          {errors.length ? (
            <details className="mb-6 rounded-lg border border-amber-300/20 bg-amber-300/[0.04] px-4 py-3 text-sm text-amber-100/75">
              <summary className="cursor-pointer">Some research artifacts are unavailable ({errors.length})</summary>
              <p className="mt-2 text-xs leading-5 text-amber-100/60">{errors.join(" ")}</p>
            </details>
          ) : null}

          {activeStudy === "math500" ? <MathStudy {...props} /> : null}
          {activeStudy === "gsm8k" ? <GsmStudy results={props.gsm8k} /> : null}
          {activeStudy === "escalation" ? <EscalationPage {...props} /> : null}
          {activeStudy === "audit" ? <AuditPage {...props} /> : null}
          {activeStudy === "literature" ? <LiteraturePage {...props} /> : null}

          <footer className="mt-20 grid gap-4 border-t border-line py-8 text-xs text-slate-600 sm:grid-cols-[1fr_auto] sm:items-end">
            <div>
              <a href={PUBLIC_REPO} target="_blank" rel="noreferrer" className="text-slate-400 transition hover:text-cyan">Public code + preregistration ↗</a>
              <p className="mt-2">Agent X-Ray · research artifact · 2026</p>
            </div>
            <dl className="metric grid grid-cols-2 gap-x-6 gap-y-2 text-right sm:grid-cols-1">
              <div><dt className="inline text-slate-700">TOTAL LIVE SPEND </dt><dd className="inline text-slate-300">{formatTotalSpend(spend.totalUsd)}</dd></div>
              <div><dt className="inline text-slate-700">MODEL </dt><dd className="inline text-slate-300">{modelName}</dd></div>
            </dl>
          </footer>
        </main>
      </div>
    </div>
  );
}

function MathStudy({ math500, primaryContrast, calibration }: DashboardProps) {
  const variants = math500?.variants ?? {};
  return (
    <>
      {math500 && primaryContrast ? <VerdictBanner results={math500} primaryContrast={primaryContrast} /> : <MissingPanel title="Primary MATH-500 contrast unavailable" detail="The paired primary contrast and flagship result summary are loaded independently; available panels remain visible below." />}
      <Section eyebrow="Efficiency frontier" title="MATH-500 accuracy against measured cost" description="Seven systems on the same 500 items. Whiskers are 95% Wilson intervals; cost is realized mean USD per item.">
        {Object.keys(variants).length ? <ParetoChart variants={variants} /> : <EmptyState label="MATH-500 frontier data is not available." />}
      </Section>
      <Section eyebrow="Budget calibration" title="Exact-budget matching, frozen before analysis" description="Calibration values document how sequential samples and escalation increments were selected for the confirmatory run.">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Fact label="Calibration items" value={finite(calibration?.n) ? `${calibration.n}` : "—"} />
          <Fact label="SC budget samples" value={finite(calibration?.sc_budget_n) ? `${calibration.sc_budget_n}` : "—"} />
          <Fact label="Escalation extra samples" value={finite(calibration?.escalate_sc_extra_samples) ? `${calibration.escalate_sc_extra_samples}` : "—"} />
          <Fact label="Full mean cost" value={usd(calibration?.full_mean_cost_usd)} />
        </div>
      </Section>
    </>
  );
}

function GsmStudy({ results }: { results: ExperimentResults | null }) {
  const variants = results?.variants ?? {};
  if (!results) return <MissingPanel title="GSM8K anchor unavailable" detail="Add the finalized n=100 result file and refresh." />;
  return (
    <>
      <VerdictBanner results={results} />
      <Section eyebrow="Anchor frontier" title="GSM8K accuracy against measured cost" description="The retained pilot anchor: seven variants on a fixed n=100 sample, shown descriptively rather than as the confirmatory claim.">
        <ParetoChart variants={variants} />
      </Section>
      <Section eyebrow="Component ablations" title="Local dismantling effects" description="Original one-at-a-time ablations are retained as pilot evidence; they are not interpreted as causal component attribution.">
        <ComponentAttribution variants={variants} />
      </Section>
    </>
  );
}

function EscalationPage({ math500, escalationAnalysis }: DashboardProps) {
  return (
    <Section eyebrow="Secondary analysis S1" title="Does structure help when agreement breaks?" description="Both arms start with SC@3. Only disagreement items trigger equal-budget structured or sequential-sampling escalation.">
      <EscalationStudy results={math500} analysis={escalationAnalysis} />
    </Section>
  );
}

function AuditPage({ audit }: DashboardProps) {
  return (
    <Section eyebrow="Label integrity S4" title="Blind human audit queue" description="All consensus-against-gold flags plus a random 50-item audit. Human verdict fields remain authoritative and update on refresh.">
      <LabelAudit audit={audit} />
    </Section>
  );
}

function LiteraturePage({ literature }: DashboardProps) {
  return (
    <Section eyebrow="Published context" title="Literature mode" description="Reported AFlow and MaAS numbers are shown as published—not normalized—and separated from Agent X-Ray measurements.">
      <LiteratureMode literature={literature} />
    </Section>
  );
}

function Section({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: ReactNode }) {
  return (
    <section className="mt-16 first:mt-0">
      <header className="mb-7 grid gap-3 md:grid-cols-2 md:items-end">
        <div><p className="font-mono text-[11px] uppercase tracking-[0.2em] text-cyan/80">{eyebrow}</p><h2 className="mt-3 text-2xl font-semibold tracking-tight text-white md:text-3xl">{title}</h2></div>
        <p className="max-w-xl text-sm leading-6 text-slate-500 md:justify-self-end">{description}</p>
      </header>
      <div className="panel-grid rounded-2xl border border-line bg-panel/75 p-4 shadow-glow sm:p-6 md:p-8">{children}</div>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-line bg-ink/50 p-5"><p className="text-[10px] uppercase tracking-[0.14em] text-slate-600">{label}</p><p className="metric mt-3 text-xl text-slate-100">{value}</p></div>;
}

function MissingPanel({ title, detail }: { title: string; detail: string }) {
  return <section className="rounded-2xl border border-dashed border-amber-300/30 bg-amber-300/[0.035] p-8"><p className="font-mono text-xs uppercase tracking-[0.2em] text-amber-300">Artifact pending</p><h2 className="mt-4 text-2xl font-semibold text-white">{title}</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">{detail}</p></section>;
}

function EmptyState({ label }: { label: string }) {
  return <div className="flex min-h-72 items-center justify-center rounded-xl border border-dashed border-line text-sm text-slate-500">{label}</div>;
}

function formatTotalSpend(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `$${value.toFixed(2)}`;
}
