import { Dashboard } from "../components/Dashboard";
import { loadDashboardData, STUDY_IDS, type StudyId } from "../lib-data";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function selectStudy(value: string | string[] | undefined): StudyId {
  const candidate = Array.isArray(value) ? value[0] : value;
  return STUDY_IDS.find((study) => study === candidate) ?? "math500";
}

export default async function Page({ searchParams }: { searchParams: Promise<{ study?: string | string[] }> }) {
  const params = await searchParams;
  const data = await loadDashboardData();
  return <Dashboard {...data} activeStudy={selectStudy(params.study)} />;
}
