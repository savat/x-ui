import SettingsClient from "@/components/SettingsClient";
import { serverApi } from "@/lib/server";
import type { Audit, Settings } from "@/lib/types";

export default async function SettingsPage() {
  const [settings, audit] = await Promise.all([
    serverApi<Settings>("/settings"),
    serverApi<Audit[]>("/audit?limit=100"),
  ]);
  return <SettingsClient settings={settings} audit={audit} />;
}
