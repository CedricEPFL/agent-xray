import type { ExperimentResults, PrimaryContrast } from "../lib-data";
import { finite, percent, pp, usd } from "./format";

const PREREGISTRATION_URL = "https://github.com/CedricEPFL/agent-xray/tree/prereg-v1";

export function VerdictBanner({
  results,
  primaryContrast,
}: {
  results: ExperimentResults;
  primaryContrast?: PrimaryContrast | null;
}) {
  if (primaryContrast) return <PrimaryVerdict results={results} contrast={primaryContrast} />;

  const metadata = results.metadata ?? {};
  const verdict = results.verdict;
  const isMock = metadata.model?.toLowerCase().startsWith("mock") ?? false;
  const isPartial = metadata.partial_run === true;
  const gain = verdict?.gain_percentage_points;
  const toneClasses = toneFor(gain);

  if (!verdict || !finite(verdict.verdict_n) || verdict.verdict_n === 0) {
    return (
      <section className="rounded-2xl border border-amber-400/25 bg-amber-300/[0.05] p-7 shadow-glow">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-amber-300">Verdict pending</p>
          <RunBadges isMock={isMock} isPartial={isPartial} completed={metadata.completed_sample_size} requested={metadata.requested_sample_size} />
        </div>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Does the workflow earn its cost?</h1>
        <p className="mt-3 max-w-2xl text-slate-400">No shared completed problems exist across the workflow and its self-consistency baseline yet.</p>
      </section>
    );
  }

  return (
    <section className={`overflow-hidden rounded-2xl border p-7 shadow-glow md:p-9 ${toneClasses}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-slate-400">Compute-matched anchor verdict</p>
        <RunBadges isMock={isMock} isPartial={isPartial} completed={metadata.completed_sample_size} requested={metadata.requested_sample_size} />
      </div>
      <div className="mt-8 grid gap-8 lg:grid-cols-[1.35fr_1fr] lg:items-end">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white md:text-5xl">Does the workflow earn its cost?</h1>
          <div className="mt-5 flex items-baseline gap-3">
            <span className="metric text-5xl font-medium md:text-7xl">{pp(gain)}</span>
            <span className="max-w-48 text-sm leading-5 text-slate-400">accuracy vs. {verdict.cost_matched_variant ?? "baseline"}</span>
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

function PrimaryVerdict({ results, contrast }: { results: ExperimentResults; contrast: PrimaryContrast }) {
  const deltaPp = finite(contrast.delta) ? contrast.delta * 100 : undefined;
  const ci = contrast.bootstrap_ci;
  const ciLabel = finite(ci?.lower) && finite(ci?.upper)
    ? `[${signedPp(ci.lower)}, ${signedPp(ci.upper)}]`
    : "—";
  const pLabel = finite(contrast.mcnemar_p) ? contrast.mcnemar_p.toFixed(3) : "—";
  const levels = contrast.stratum_levels?.length ? `L${contrast.stratum_levels.join("–")}` : "hard strata";

  return (
    <section className={`overflow-hidden rounded-2xl border p-7 shadow-glow md:p-9 ${toneFor(deltaPp)}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-slate-400">Primary confirmatory contrast · {levels}</p>
        <a
          href={PREREGISTRATION_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-full border border-cyan/35 bg-cyan/[0.08] px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan transition hover:bg-cyan/[0.14]"
        >
          Preregistered ↗
        </a>
      </div>
      <div className="mt-8 grid gap-8 lg:grid-cols-[1.25fr_1fr] lg:items-end">
        <div>
          <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-white md:text-5xl">Structure did not separate from exact-budget self-consistency.</h1>
          <div className="mt-6 flex flex-wrap items-baseline gap-x-3 gap-y-2">
            <span className="metric text-5xl font-medium md:text-7xl">{pp(deltaPp)}</span>
            <span className="max-w-56 text-sm leading-5 text-slate-400">{contrast.system_a ?? "full"} minus {contrast.system_b ?? "sc@budget"}</span>
          </div>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-slate-400">
            The paired bootstrap interval includes zero; the exact McNemar test finds no detectable difference at this sample size.
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-white/10 bg-white/10">
          <Metric label={`${contrast.system_a ?? "Full"} accuracy`} value={percent(contrast.acc_a)} />
          <Metric label={`${contrast.system_b ?? "Baseline"} accuracy`} value={percent(contrast.acc_b)} />
          <Metric label="95% paired bootstrap CI" value={ciLabel} wide />
          <Metric label="Exact McNemar p" value={pLabel} />
          <Metric label="Analyzed pairs" value={finite(contrast.n_pairs) ? `${contrast.n_pairs}` : "—"} />
        </dl>
      </div>
      <p className="metric mt-5 text-[10px] uppercase tracking-[0.12em] text-slate-500">
        Model {results.metadata?.model ?? "pending"} · exclusions {contrast.exclusions ?? "—"} · item-clustered pairs
      </p>
    </section>
  );
}

function signedPp(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`;
}

function toneFor(value: number | null | undefined): string {
  if (!finite(value) || value === 0) return "border-slate-500/30 bg-slate-400/[0.04] text-slate-200";
  return value > 0
    ? "border-emerald-400/30 bg-emerald-400/[0.06] text-emerald-300"
    : "border-rose-400/30 bg-rose-400/[0.06] text-rose-300";
}

function RunBadges({ isMock, isPartial, completed, requested }: { isMock: boolean; isPartial: boolean; completed?: number; requested?: number }) {
  if (!isMock && !isPartial) return null;
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {isMock ? <span className="rounded-full border border-amber-300/40 bg-amber-300/10 px-3 py-1 font-mono text-[11px] font-semibold tracking-[0.16em] text-amber-200">SYNTHETIC MOCK DATA</span> : null}
      {isPartial ? <span className="rounded-full border border-amber-300/40 bg-amber-300/10 px-3 py-1 font-mono text-[11px] font-semibold tracking-[0.16em] text-amber-200">PARTIAL RUN — n={finite(completed) ? completed : "—"}/{finite(requested) ? requested : "—"}</span> : null}
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
