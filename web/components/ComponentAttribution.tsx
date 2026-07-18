import type { VariantResult } from "../lib-data";
import { finite, pp } from "./format";

const ABLATIONS = [
  { variant: "-critique", component: "critique" },
  { variant: "-revise", component: "revise" },
  { variant: "-vote", component: "vote" },
];

export function ComponentAttribution({ variants }: { variants: Record<string, VariantResult> }) {
  const full = variants.full;
  const rows = ABLATIONS.map(({ variant, component }) => {
    const item = variants[variant];
    const derivedDelta = finite(item?.accuracy) && finite(full?.accuracy) ? item.accuracy - full.accuracy : undefined;
    return {
      variant,
      component,
      delta: finite(item?.accuracy_delta_vs_full) ? item.accuracy_delta_vs_full : derivedDelta,
      share: full?.per_component_cost_share?.[component],
    };
  });
  const maxAbs = Math.max(0.01, ...rows.map((row) => Math.abs(row.delta ?? 0)));

  return (
    <div className="space-y-7">
      <div className="grid gap-3 text-[11px] uppercase tracking-[0.14em] text-slate-500 md:grid-cols-[120px_1fr_230px]">
        <span>Removed</span><span>Accuracy delta vs. full · percentage points</span><span>Share of full cost · %</span>
      </div>
      {rows.map((row) => {
        const delta = row.delta;
        const positive = finite(delta) && delta > 0;
        const negative = finite(delta) && delta < 0;
        const width = finite(delta) ? (Math.abs(delta) / maxAbs) * 48 : 0;
        const share = finite(row.share) ? row.share : 0;
        return (
          <div key={row.variant} className="grid items-center gap-3 md:grid-cols-[120px_1fr_230px]">
            <div>
              <p className="font-medium text-slate-100">{row.component}</p>
              <p className="metric mt-1 text-xs text-slate-500">{row.variant}</p>
            </div>
            <div className="relative h-11 rounded-lg border border-line/80 bg-ink/70">
              <div className="absolute inset-y-0 left-1/2 w-px bg-slate-500/50" />
              {finite(delta) ? (
                <div
                  className={`absolute top-2 h-7 rounded-sm ${positive ? "bg-rose-400/75" : negative ? "bg-emerald-400/75" : "bg-slate-500/70"}`}
                  style={positive ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${Math.max(width, delta === 0 ? 1 : 0)}%` }}
                />
              ) : null}
              <span className="metric absolute inset-0 flex items-center justify-center text-xs font-semibold text-white drop-shadow">{finite(delta) ? pp(delta * 100) : "pending"}</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-800">
                <div className="h-full rounded-full bg-cyan/75" style={{ width: `${Math.max(0, Math.min(100, share * 100))}%` }} />
              </div>
              <span className="metric w-16 text-right text-sm text-cyan-100">{finite(row.share) ? `${(row.share * 100).toFixed(1)}%` : "—"}</span>
            </div>
          </div>
        );
      })}
      <div className="flex flex-wrap gap-x-6 gap-y-2 border-t border-line/70 pt-5 text-xs text-slate-500">
        <span><i className="mr-2 inline-block h-2 w-2 rounded-sm bg-rose-400" />Removing helps</span>
        <span><i className="mr-2 inline-block h-2 w-2 rounded-sm bg-emerald-400" />Removing hurts</span>
        <span>The −vote row removes the full sampling + vote block (3 → 1 candidate).</span>
      </div>
    </div>
  );
}
