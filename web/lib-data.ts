import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

export const STUDY_IDS = ["math500", "gsm8k", "escalation", "audit", "literature"] as const;
export type StudyId = (typeof STUDY_IDS)[number];

export type ConfidenceInterval = {
  lower?: number;
  upper?: number;
  level?: number;
};

export type VariantResult = {
  n?: number;
  correct?: number;
  accuracy?: number;
  ci?: ConfidenceInterval;
  mean_cost_usd?: number;
  cost_per_success_usd?: number | null;
  per_component_cost_share?: Record<string, number>;
  accuracy_delta_vs_full?: number;
};

export type ExperimentResults = {
  metadata?: {
    model?: string;
    temperature?: number;
    sample_size?: number;
    seed?: number;
    repeat_count?: number;
    partial_run?: boolean;
    completed_sample_size?: number;
    requested_sample_size?: number;
    checkpoint_rows?: number;
  };
  study?: string;
  variants?: Record<string, VariantResult>;
  verdict?: {
    cost_matched_variant?: string | null;
    verdict_n?: number;
    full_accuracy?: number | null;
    baseline_accuracy?: number | null;
    full_mean_cost_usd?: number | null;
    baseline_mean_cost_usd?: number | null;
    gain_percentage_points?: number | null;
  };
};

export type PrimaryContrast = {
  run_id?: string;
  system_a?: string;
  system_b?: string;
  stratum_levels?: number[];
  n_pairs?: number;
  acc_a?: number | null;
  acc_b?: number | null;
  delta?: number | null;
  mcnemar_p?: number | null;
  bootstrap_ci?: ConfidenceInterval & { n_boot?: number };
  exclusions?: number;
};

export type CalibrationData = {
  model?: string;
  n?: number;
  sc_budget_n?: number;
  escalate_sc_extra_samples?: number;
  full_mean_cost_usd?: number;
  cot_sample_mean_cost_usd?: number;
  escalate_structure_mean_incremental_cost_usd?: number;
  source_run_id?: string;
};

export type AuditItem = {
  item_id?: string;
  dataset?: string;
  problem_id?: string;
  problem?: string;
  gold_answer?: string;
  consensus_answer?: string | null;
  model_answers?: string[];
  scoring_methods?: string[];
  selection_reason?: string;
  category?: string;
  verdict?: string;
  notes?: string;
};

export type AuditSheet = {
  metadata?: {
    audit_items?: number;
    consensus_candidates?: number;
    random_sample_selected?: number;
    instructions?: string;
  };
  items?: AuditItem[];
};

export type LiteratureData = {
  description?: string;
  sources?: Record<string, string>;
  aflow_table1_gsm8k?: Record<string, number | Record<string, number>>;
  maas_table1_gsm8k?: Record<string, number>;
  maas_table3_math_inference?: Record<string, string | { acc?: number; usd?: number }>;
  audit_observations?: string[];
};

export type SpendSummary = {
  totalUsd: number;
  ledgerFiles: number;
  ledgerRows: number;
};

export type DashboardData = {
  math500: ExperimentResults | null;
  gsm8k: ExperimentResults | null;
  primaryContrast: PrimaryContrast | null;
  escalationAnalysis: PrimaryContrast | null;
  calibration: CalibrationData | null;
  audit: AuditSheet | null;
  literature: LiteratureData | null;
  spend: SpendSummary;
  modelName: string;
  errors: string[];
};

type ReadResult<T> = { data: T | null; error?: string };

async function readJson<T>(filePath: string, label: string): Promise<ReadResult<T>> {
  try {
    const text = await readFile(filePath, "utf-8");
    return { data: JSON.parse(text) as T };
  } catch {
    return { data: null, error: `${label} is not available yet.` };
  }
}

async function sumLiveSpend(resultsRoot: string): Promise<ReadResult<SpendSummary>> {
  try {
    const filenames = (await readdir(resultsRoot)).filter((name) => /^ledger_live.*\.jsonl$/.test(name));
    const ledgers = await Promise.all(filenames.map((name) => readFile(path.join(resultsRoot, name), "utf-8")));
    let totalUsd = 0;
    let ledgerRows = 0;
    for (const ledger of ledgers) {
      for (const line of ledger.split(/\r?\n/)) {
        if (!line.trim()) continue;
        try {
          const row = JSON.parse(line) as { usd_cost?: unknown };
          if (typeof row.usd_cost === "number" && Number.isFinite(row.usd_cost)) totalUsd += row.usd_cost;
          ledgerRows += 1;
        } catch {
          // A live writer can leave its final line incomplete; ignore that line until the next request.
        }
      }
    }
    return { data: { totalUsd, ledgerFiles: filenames.length, ledgerRows } };
  } catch {
    return {
      data: { totalUsd: 0, ledgerFiles: 0, ledgerRows: 0 },
      error: "Live spend ledgers are not available yet.",
    };
  }
}

export async function loadDashboardData(): Promise<DashboardData> {
  const webRoot = process.cwd();
  const resultsRoot = path.resolve(webRoot, "../results");
  const [math500, gsm8k, primaryContrast, escalationAnalysis, calibration, audit, literature, spend] = await Promise.all([
    readJson<ExperimentResults>(path.join(resultsRoot, "results_math500_final.json"), "MATH-500 results"),
    readJson<ExperimentResults>(path.join(resultsRoot, "results_gsm8k_n100_final.json"), "GSM8K anchor results"),
    readJson<PrimaryContrast>(path.join(resultsRoot, "primary_contrast.json"), "Primary contrast"),
    readJson<PrimaryContrast>(path.join(resultsRoot, "analysis_live_math500_n500_seed42_r1.json"), "Escalation analysis provenance"),
    readJson<CalibrationData>(path.join(resultsRoot, "calibration_math500.json"), "MATH-500 calibration"),
    readJson<AuditSheet>(path.join(resultsRoot, "audit_sheet.json"), "Label-audit sheet"),
    readJson<LiteratureData>(path.resolve(webRoot, "../../literature-data.json"), "Literature data"),
    sumLiveSpend(resultsRoot),
  ]);
  const modelName = math500.data?.metadata?.model ?? gsm8k.data?.metadata?.model ?? calibration.data?.model ?? "pending";

  return {
    math500: math500.data,
    gsm8k: gsm8k.data,
    primaryContrast: primaryContrast.data,
    escalationAnalysis: escalationAnalysis.data,
    calibration: calibration.data,
    audit: audit.data,
    literature: literature.data,
    spend: spend.data ?? { totalUsd: 0, ledgerFiles: 0, ledgerRows: 0 },
    modelName,
    errors: [
      math500.error,
      gsm8k.error,
      primaryContrast.error,
      escalationAnalysis.error,
      calibration.error,
      audit.error,
      literature.error,
      spend.error,
    ].filter((error): error is string => Boolean(error)),
  };
}
