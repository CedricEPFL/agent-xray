import type { VariantResult } from "../lib-data";
import { compactUsd, finite, percent } from "./format";

type Point = { name: string; accuracy: number; cost: number; lower: number; upper: number; baseline: boolean };

const BASELINES = new Set(["cot@1", "sc@3", "sc@5"]);

export function ParetoChart({ variants }: { variants: Record<string, VariantResult> }) {
  const points: Point[] = Object.entries(variants).flatMap(([name, item]) => {
    if (!finite(item.accuracy) || !finite(item.mean_cost_usd) || item.mean_cost_usd <= 0) return [];
    return [{
      name,
      accuracy: item.accuracy,
      cost: item.mean_cost_usd,
      lower: finite(item.ci?.lower) ? item.ci.lower : item.accuracy,
      upper: finite(item.ci?.upper) ? item.ci.upper : item.accuracy,
      baseline: BASELINES.has(name),
    }];
  });

  if (!points.length) return <EmptyChart />;

  const width = 840;
  const height = 460;
  const margin = { left: 74, right: 42, top: 38, bottom: 68 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const costs = points.map((point) => point.cost);
  let logMin = Math.log10(Math.min(...costs)) - 0.12;
  let logMax = Math.log10(Math.max(...costs)) + 0.12;
  if (logMax - logMin < 0.5) {
    const midpoint = (logMin + logMax) / 2;
    logMin = midpoint - 0.25;
    logMax = midpoint + 0.25;
  }
  const x = (cost: number) => margin.left + ((Math.log10(cost) - logMin) / (logMax - logMin)) * plotW;
  const y = (accuracy: number) => margin.top + (1 - Math.max(0, Math.min(1, accuracy))) * plotH;
  const xTicks = Array.from({ length: 5 }, (_, index) => 10 ** (logMin + (index / 4) * (logMax - logMin)));
  const yTicks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[680px]" role="img" aria-label="Accuracy versus mean cost per problem with 95 percent confidence intervals">
        <defs>
          <filter id="pointGlow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        {yTicks.map((tick) => (
          <g key={tick}>
            <line x1={margin.left} x2={width - margin.right} y1={y(tick)} y2={y(tick)} stroke="#263343" strokeDasharray="3 6" />
            <text x={margin.left - 14} y={y(tick) + 4} textAnchor="end" fill="#718096" fontSize="12" className="metric">{Math.round(tick * 100)}%</text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <g key={tick}>
            <line x1={x(tick)} x2={x(tick)} y1={margin.top} y2={height - margin.bottom} stroke="#1d2836" />
            <text x={x(tick)} y={height - margin.bottom + 24} textAnchor="middle" fill="#718096" fontSize="11" className="metric">{compactUsd(tick)}</text>
          </g>
        ))}
        <line x1={margin.left} x2={margin.left} y1={margin.top} y2={height - margin.bottom} stroke="#405064" />
        <line x1={margin.left} x2={width - margin.right} y1={height - margin.bottom} y2={height - margin.bottom} stroke="#405064" />
        <text x={margin.left + plotW / 2} y={height - 14} textAnchor="middle" fill="#9aa9ba" fontSize="13">Mean cost per problem · USD · log scale</text>
        <text transform={`translate(18 ${margin.top + plotH / 2}) rotate(-90)`} textAnchor="middle" fill="#9aa9ba" fontSize="13">Exact-match accuracy · %</text>
        {points.map((point, index) => {
          const px = x(point.cost);
          const py = y(point.accuracy);
          const color = point.baseline ? "#58d7e8" : "#a6e36f";
          const labelY = py + (index % 2 === 0 ? -13 : 22);
          return (
            <g key={point.name}>
              <line x1={px} x2={px} y1={y(point.upper)} y2={y(point.lower)} stroke={color} strokeWidth="2" opacity="0.72" />
              <line x1={px - 5} x2={px + 5} y1={y(point.upper)} y2={y(point.upper)} stroke={color} opacity="0.72" />
              <line x1={px - 5} x2={px + 5} y1={y(point.lower)} y2={y(point.lower)} stroke={color} opacity="0.72" />
              {point.baseline ? (
                <rect x={px - 6} y={py - 6} width="12" height="12" rx="1" transform={`rotate(45 ${px} ${py})`} fill={color} filter="url(#pointGlow)" />
              ) : (
                <circle cx={px} cy={py} r={point.name === "full" ? 7 : 5.5} fill={color} stroke={point.name === "full" ? "white" : "none"} strokeWidth="1.5" filter="url(#pointGlow)" />
              )}
              <text x={px + 9} y={labelY} fill="#dce6ef" fontSize="12" fontWeight={point.name === "full" ? 700 : 500}>{point.name}</text>
              <title>{`${point.name}: ${percent(point.accuracy)} accuracy, ${compactUsd(point.cost)} per problem`}</title>
            </g>
          );
        })}
        <g transform={`translate(${width - 262} 18)`}>
          <circle cx="0" cy="0" r="5" fill="#a6e36f" /><text x="12" y="4" fill="#91a0b1" fontSize="11">workflow / ablation</text>
          <rect x="134" y="-5" width="10" height="10" transform="rotate(45 139 0)" fill="#58d7e8" /><text x="154" y="4" fill="#91a0b1" fontSize="11">baseline</text>
        </g>
      </svg>
    </div>
  );
}

function EmptyChart() {
  return <div className="flex min-h-80 items-center justify-center rounded-xl border border-dashed border-line text-sm text-slate-500">Waiting for cost and accuracy measurements.</div>;
}
