import { Dashboard } from "../components/Dashboard";
import { loadDashboardData } from "../lib-data";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function Page() {
  const data = await loadDashboardData();
  return <Dashboard {...data} />;
}
