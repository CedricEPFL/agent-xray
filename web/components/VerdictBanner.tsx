import type { ExperimentResults } from "../lib-data";
import { finite, percent, pp, usd } from "./format";

export function VerdictBanner({ results }: { results: ExperimentResults }) {
  const metadata = results.metadata ?? {};
  const verdict = results.verdict;
  const isMock = metadata.model?.toLowerCase().startsWith("mock") ?? false;
  const isPartial = metadata.partial_run === true;
  const gain = verdict?.gain_percentage_points;
  const tone = !finite(gain) || gain === 0 ? "neutral" : gain > 0 ? "positive" : "negative";
  const toneClasses = {
    positive: "border-emerald-400/30 bg-emerald-400/[0.06] text-emerald-300",
    negative: "border-rose-400/30 bg-rose-400/[0.06] text-rose-300",
    neutral: "border-slate-500/30 bg-slate-400/[0.04] text-slate-200",
  }[tone];

  if (!verdict || !finite(verdict.verdict_n) || verdict.verdict_n === 0) {
    return (
      <section id="verdict" className="section-anchor rounded-2xl border border-amber-400/25 bg-amber-300/[0.05] p-7 shadow-glow">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-amber-300">Verdict pending</p>
          <RunBadges isMock={isMock} isPartial={isPartial} completed={metadata.completed_sample_size} requested={metadata.requested_sample_size} />
        </div>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Does the workflow earn its cost?</h1>
        <p className="mt-3 max-w-2xl text-slate-400">No shared completed problems exist across the full workflow and all three self-consistency baselines yet. Continue the experiment, then refresh this page.</p>
      </section>
    );
  }

  return (
    <section id="verdict" className={`section-anchor overflow-hidden rounded-2xl border p-7 shadow-glow md:p-9 ${toneClasses}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-slate-400">Compute-matched verdict</p>
        <RunBadges isMock={isMock} isPartial={isPartial} completed={metadata.completed_sample_size} requested={metadata.requested_sample_size} />
      </div>
      <div className="mt-8 grid gap-8 lg:grid-cols-[1.35fr_1fr] lg:items-end">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">Does the workflow earn its cost?</h1>
          <div className="mt-5 flex items-baseline gap-3">
            <span className="metric text-5xl font-medium md:text-7xl">{pp(gain)}</span>
            <span className="max-w-48 text-sm leading-5 text-slate-400">accuracy vs. cost-matched {verdict.cost_matched_variant ?? "baseline"}</span>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-white/10 bg-white/10">
          <Metric label="Full accuracy" value={percent(verdict.full_accuracy)} />
          <Metric label="Baseline accuracy" value={percent(verdict.baseline_accuracy)} />
          <Metric label="Full cost / problem" value={usd(verdict.full_mean_cost_usd)} />
          <Metric label="Baseline cost / problem" value={usd(verdict.baseline_mean_cost_usd)} />
          <Metric label="Shared verdict n" value={`${verdict.verdict_n}`} wide />
        </dl>
      </div>
    </section>
  );
}

function RunBadges({ isMock, isPartial, completed, requested }: { isMock: boolean; isPartial: boolean; completed?: number; requested?: number }) {
  if (!isMock && !isPartial) return null;
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {isMock ? (
        <span className="rounded-full border border-amber-300/40 bg-amber-300/10 px-3 py-1 font-mono text-[11px] font-semibold tracking-[0.16em] text-amber-200">
          SYNTHETIC MOCK DATA
        </span>
      ) : null}
      {isPartial ? (
        <span className="rounded-full border border-amber-300/40 bg-amber-300/10 px-3 py-1 font-mono text-[11px] font-semibold tracking-[0.16em] text-amber-200">
          PARTIAL RUN — n={finite(completed) ? completed : "—"}/{finite(requested) ? requested : "—"}
        </span>
      ) : null}
    </div>
  );
}

function Metric({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={`bg-ink/70 p-4 ${wide ? "col-span-2" : ""}`}>
      <dt className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{label}</dt>
      <dd className="metric mt-2 text-lg text-slate-100">{value}</dd>
    </div>
  );
}
