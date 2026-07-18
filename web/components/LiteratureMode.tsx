import type { LiteratureData } from "../lib-data";
import { finite } from "./format";

export function LiteratureMode({ literature }: { literature: LiteratureData | null }) {
  if (!literature) {
    return <div className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-slate-500">Literature data is unavailable. Add <span className="font-mono">poc/literature-data.json</span> and refresh.</div>;
  }
  const aflow = Object.entries(literature.aflow_table1_gsm8k ?? {}).filter((entry): entry is [string, number] => finite(entry[1]));
  const maas = Object.entries(literature.maas_table1_gsm8k ?? {}).filter((entry): entry is [string, number] => finite(entry[1]));
  const inference = Object.entries(literature.maas_table3_math_inference ?? {}).flatMap(([name, value]) => {
    if (typeof value === "object" && value && finite(value.acc) && finite(value.usd)) return [{ name, acc: value.acc, usd: value.usd }];
    return [];
  });

  return (
    <div className="space-y-10">
      <div className="grid gap-5 xl:grid-cols-2">
        <PublishedTable title="AFlow · Table 1" source={literature.sources?.aflow} rows={aflow} highlight="AFlow" />
        <PublishedTable title="MaAS · Table 1" source={literature.sources?.maas} rows={maas} highlight="MaAS" />
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
        <div className="rounded-xl border border-line bg-ink/45 p-5 md:p-7">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
            <div><p className="font-mono text-[11px] uppercase tracking-[0.18em] text-cyan">MaAS · Table 3</p><h3 className="mt-2 text-lg font-medium text-white">MATH inference Pareto</h3></div>
            <p className="text-xs text-slate-500">accuracy (%) vs. inference cost (USD)</p>
          </div>
          <MiniPareto points={inference} />
        </div>
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-amber-300">Audit observations</p>
          <div className="mt-4 space-y-3">
            {(literature.audit_observations ?? []).map((observation, index) => (
              <article key={observation} className="rounded-xl border border-amber-200/15 bg-amber-200/[0.035] p-4">
                <div className="flex gap-3"><span className="metric text-xs text-amber-300/70">{String(index + 1).padStart(2, "0")}</span><p className="text-sm leading-6 text-slate-300">{observation}</p></div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PublishedTable({ title, source, rows, highlight }: { title: string; source?: string; rows: [string, number][]; highlight: string }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-ink/45">
      <div className="border-b border-line px-5 py-4"><h3 className="font-medium text-white">{title}</h3><p className="mt-1 text-xs text-slate-500">Published GSM8K exact-match accuracy · %</p></div>
      <table className="w-full text-sm"><thead><tr className="text-left text-[10px] uppercase tracking-[0.15em] text-slate-500"><th className="px-5 py-3 font-medium">Method</th><th className="px-5 py-3 text-right font-medium">Accuracy</th></tr></thead>
        <tbody>{rows.map(([name, value]) => <tr key={name} className={`border-t border-line/60 ${name === highlight ? "bg-cyan/[0.06]" : ""}`}><td className="px-5 py-3 text-slate-300">{name.replaceAll("_", " ")}</td><td className="metric px-5 py-3 text-right text-slate-100">{value.toFixed(2)}%</td></tr>)}</tbody>
      </table>
      {source ? <p className="border-t border-line px-5 py-3 text-[11px] leading-5 text-slate-600">{source}</p> : null}
    </div>
  );
}

function MiniPareto({ points }: { points: { name: string; acc: number; usd: number }[] }) {
  if (!points.length) return <div className="flex h-64 items-center justify-center text-sm text-slate-500">No inference data.</div>;
  const width = 570, height = 285, left = 58, right = 24, top = 24, bottom = 52;
  const maxUsd = Math.max(...points.map((point) => point.usd)) * 1.08;
  const minAcc = Math.floor(Math.min(...points.map((point) => point.acc)) - 2);
  const maxAcc = Math.ceil(Math.max(...points.map((point) => point.acc)) + 2);
  const x = (cost: number) => left + (cost / maxUsd) * (width - left - right);
  const y = (acc: number) => top + ((maxAcc - acc) / (maxAcc - minAcc)) * (height - top - bottom);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Published MATH accuracy versus inference cost">
      {[minAcc, (minAcc + maxAcc) / 2, maxAcc].map((tick) => <g key={tick}><line x1={left} x2={width-right} y1={y(tick)} y2={y(tick)} stroke="#263343" strokeDasharray="3 5" /><text x={left-10} y={y(tick)+4} textAnchor="end" fill="#718096" fontSize="11">{tick.toFixed(0)}%</text></g>)}
      {[0, maxUsd/2, maxUsd].map((tick) => <g key={tick}><line x1={x(tick)} x2={x(tick)} y1={top} y2={height-bottom} stroke="#1d2836" /><text x={x(tick)} y={height-bottom+22} textAnchor="middle" fill="#718096" fontSize="11">${tick.toFixed(2)}</text></g>)}
      <line x1={left} x2={width-right} y1={height-bottom} y2={height-bottom} stroke="#405064" />
      {points.map((point) => <g key={point.name}><circle cx={x(point.usd)} cy={y(point.acc)} r={point.name === "MaAS" ? 7 : 5} fill={point.name === "MaAS" ? "#a6e36f" : "#58d7e8"} /><text x={x(point.usd)+9} y={y(point.acc)-9} fill="#dce6ef" fontSize="11">{point.name}</text><title>{`${point.name}: ${point.acc}% at $${point.usd}`}</title></g>)}
      <text x={left+(width-left-right)/2} y={height-7} textAnchor="middle" fill="#9aa9ba" fontSize="12">Inference cost · USD</text>
    </svg>
  );
}
