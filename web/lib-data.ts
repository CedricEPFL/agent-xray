import { readFile } from "node:fs/promises";

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
    partial_run?: boolean;
    completed_sample_size?: number;
    requested_sample_size?: number;
    checkpoint_rows?: number;
  };
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

export type LiteratureData = {
  description?: string;
  sources?: Record<string, string>;
  aflow_table1_gsm8k?: Record<string, number | Record<string, number>>;
  maas_table1_gsm8k?: Record<string, number>;
  maas_table3_math_inference?: Record<string, string | { acc?: number; usd?: number }>;
  audit_observations?: string[];
};

export type DashboardData = {
  results: ExperimentResults | null;
  literature: LiteratureData | null;
  errors: string[];
};

async function readJson<T>(path: string, label: string): Promise<{ data: T | null; error?: string }> {
  try {
    const text = await readFile(path, "utf-8");
    return { data: JSON.parse(text) as T };
  } catch {
    return { data: null, error: `${label} is not available yet.` };
  }
}

export async function loadDashboardData(): Promise<DashboardData> {
  const webRoot = process.cwd();
  const [results, literature] = await Promise.all([
    readJson<ExperimentResults>(`${webRoot}/../results/results.json`, "Experiment results"),
    readJson<LiteratureData>(`${webRoot}/../../literature-data.json`, "Literature data"),
  ]);
  return {
    results: results.data,
    literature: literature.data,
    errors: [results.error, literature.error].filter((error): error is string => Boolean(error)),
  };
}
