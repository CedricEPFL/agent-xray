import type { ExperimentResults, PrimaryContrast } from "../lib-data";
import { ParetoChart } from "./ParetoChart";

// Frozen confirmatory summaries from results/analysis_live_math500_n500_seed42_r1.json.
const S1_SUMMARIES = {
  allItems: { deltaPp: -0.6, p: 0.508, n: 480 },
  escalatedOnly: { structureAccuracy: 78.1, scAccuracy: 83.6, deltaPp: -5.5, p: 0.289, n: 73 },
} as const;

const CHART_SYSTEMS = new Set(["escalate_structure", "escalate_sc", "full", "sc@budget", "cot@1"]);

export function EscalationStudy({ results, analysis }: { results: ExperimentResults | null; analysis: PrimaryContrast | null }) {
  const variants = Object.fromEntries(
    Object.entries(results?.variants ?? {}).filter(([name]) => CHART_SYSTEMS.has(name)),
  );

  return (
    <div className="space-y-10">
      <div className="grid gap-4 lg:grid-cols-2">
        <StatCard
          eyebrow="S1 · all analyzable items"
          title="Structure vs. sequential SC"
          delta={S1_SUMMARIES.allItems.deltaPp}
          p={S1_SUMMARIES.allItems.p}
          n={S1_SUMMARIES.allItems.n}
          detail="Agreement-gated arms, evaluated across the complete paired analysis set."
        />
        <StatCard
          eyebrow="S1 · escalated only"
          title="Structure 78.1% · SC 83.6%"
          delta={S1_SUMMARIES.escalatedOnly.deltaPp}
          p={S1_SUMMARIES.escalatedOnly.p}
          n={S1_SUMMARIES.escalatedOnly.n}
          detail="Among disagreement-triggered items, extra independent samples led by 5.5 points; the interval remains underpowered."
        />
      </div>
      <div>
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-cyan">Measured frontier · MATH-500</p>
            <h3 className="mt-2 text-xl font-medium text-white">Escalation policies against fixed strategies</h3>
          </div>
          <p className="metric text-[10px] uppercase tracking-[0.12em] text-slate-600">run {analysis?.run_id ?? "pending"}</p>
        </div>
        <ParetoChart variants={variants} />
      </div>
    </div>
  );
}

function StatCard({ eyebrow, title, delta, p, n, detail }: { eyebrow: string; title: string; delta: number; p: number; n: number; detail: string }) {
  return (
    <article className="rounded-xl border border-line bg-ink/55 p-5 md:p-7">
      <p className="font-mono text-[11px] uppercase tracking-[0.17em] text-cyan/80">{eyebrow}</p>
      <h3 className="mt-3 text-lg font-medium text-white">{title}</h3>
      <div className="mt-6 flex items-end justify-between gap-5">
        <div>
          <p className="metric text-4xl font-semibold text-rose-300">{delta.toFixed(1)} pp</p>
          <p className="mt-1 text-xs text-slate-500">structured escalation minus sequential SC</p>
        </div>
        <dl className="metric shrink-0 text-right text-sm">
          <div><dt className="inline text-slate-600">exact p </dt><dd className="inline text-slate-200">{p.toFixed(3)}</dd></div>
          <div className="mt-1"><dt className="inline text-slate-600">paired n </dt><dd className="inline text-slate-200">{n}</dd></div>
        </dl>
      </div>
      <p className="mt-5 border-t border-line/70 pt-4 text-sm leading-6 text-slate-500">{detail}</p>
    </article>
  );
}
