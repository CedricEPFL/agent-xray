import type { AuditItem, AuditSheet } from "../lib-data";

export function LabelAudit({ audit }: { audit: AuditSheet | null }) {
  if (!audit) {
    return <div className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-slate-500">The blind audit sheet is not available yet.</div>;
  }

  const items = audit.items ?? [];
  const filled = items.filter((item) => Boolean(item.verdict?.trim()));
  const pending = items.length - filled.length;
  const selectionCounts = countBy(items, (item) => item.category || item.selection_reason);
  const datasetCounts = countBy(items, (item) => item.dataset);
  const verdictCounts = countBy(filled, (item) => item.verdict);

  return (
    <div className="space-y-9">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label="Audit items" value={items.length} tone="text-white" />
        <SummaryCard label="Pending" value={pending} tone="text-amber-200" />
        <SummaryCard label="Verdicts filled" value={filled.length} tone="text-emerald-300" />
        <SummaryCard label="Consensus flags" value={audit.metadata?.consensus_candidates ?? selectionCounts.consensus_candidate ?? 0} tone="text-cyan" />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <CountPanel title="Selection category" counts={selectionCounts} />
        <CountPanel title="Dataset" counts={datasetCounts} />
        <CountPanel title="Human verdict" counts={Object.keys(verdictCounts).length ? verdictCounts : { pending: pending }} />
      </div>

      <div>
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-cyan">Blind audit queue</p>
            <h3 className="mt-2 text-xl font-medium text-white">Item-level adjudication status</h3>
          </div>
          <p className="max-w-xl text-xs leading-5 text-slate-500">{audit.metadata?.instructions ?? "Human verdicts are read from audit_sheet.json on each request."}</p>
        </div>
        <div className="space-y-3">
          {items.map((item, index) => <AuditRow key={item.item_id ?? `${item.dataset}-${item.problem_id}-${index}`} item={item} index={index} />)}
        </div>
      </div>
    </div>
  );
}

function AuditRow({ item, index }: { item: AuditItem; index: number }) {
  const verdict = item.verdict?.trim();
  const status = verdict || "pending";
  return (
    <details className="group rounded-xl border border-line bg-ink/45 open:border-slate-600">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 px-4 py-4 marker:hidden sm:flex-nowrap">
        <span className="metric w-8 shrink-0 text-[11px] text-slate-600">{String(index + 1).padStart(2, "0")}</span>
        <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{item.problem || "Problem text unavailable"}</span>
        <span className="metric text-[10px] uppercase tracking-[0.11em] text-slate-600">{item.dataset ?? "unknown"} · {item.selection_reason?.replaceAll("_", " ") ?? item.category ?? "uncategorized"}</span>
        <StatusChip status={status} />
      </summary>
      <div className="grid gap-5 border-t border-line px-5 py-5 text-sm lg:grid-cols-[1.5fr_1fr]">
        <div>
          <p className="leading-6 text-slate-300">{item.problem || "Problem text unavailable"}</p>
          {item.notes ? <p className="mt-4 rounded-lg border border-amber-200/15 bg-amber-200/[0.035] p-3 text-amber-100/75">Notes: {item.notes}</p> : null}
        </div>
        <dl className="space-y-3 rounded-lg border border-line/70 bg-black/15 p-4">
          <AuditField label="Item" value={item.item_id ?? "—"} />
          <AuditField label="Problem ID" value={item.problem_id ?? "—"} />
          <AuditField label="Gold" value={item.gold_answer || "—"} />
          <AuditField label="Consensus" value={item.consensus_answer || "—"} />
          <AuditField label="Model answers" value={item.model_answers?.join(" · ") || "—"} />
          <AuditField label="Scoring" value={item.scoring_methods?.join(" · ") || "—"} />
        </dl>
      </div>
    </details>
  );
}

function StatusChip({ status }: { status: string }) {
  const pending = status === "pending";
  return <span className={`shrink-0 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.11em] ${pending ? "border-amber-300/25 bg-amber-300/[0.06] text-amber-200" : "border-emerald-300/25 bg-emerald-300/[0.06] text-emerald-200"}`}>{status.replaceAll("_", " ")}</span>;
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <article className="rounded-xl border border-line bg-ink/55 p-5"><p className="text-[11px] uppercase tracking-[0.14em] text-slate-600">{label}</p><p className={`metric mt-3 text-3xl ${tone}`}>{value}</p></article>;
}

function CountPanel({ title, counts }: { title: string; counts: Record<string, number> }) {
  return (
    <div className="rounded-xl border border-line/80 bg-black/10 p-4">
      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-600">{title}</p>
      <dl className="mt-3 space-y-2">
        {Object.entries(counts).map(([label, count]) => <div key={label} className="flex items-center justify-between gap-3 text-sm"><dt className="text-slate-400">{label.replaceAll("_", " ")}</dt><dd className="metric text-slate-200">{count}</dd></div>)}
      </dl>
    </div>
  );
}

function AuditField({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-[10px] uppercase tracking-[0.12em] text-slate-600">{label}</dt><dd className="metric mt-1 break-words text-xs leading-5 text-slate-300">{value}</dd></div>;
}

function countBy(items: AuditItem[], keyFor: (item: AuditItem) => string | undefined): Record<string, number> {
  return items.reduce<Record<string, number>>((counts, item) => {
    const key = keyFor(item)?.trim();
    if (key) counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}
