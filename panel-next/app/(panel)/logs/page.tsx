import LogsClient from "@/components/LogsClient";
import { serverApi } from "@/lib/server";
import type { Service } from "@/lib/types";

export default async function LogsPage() {
  const services = await serverApi<Service[]>("/services");
  return <LogsClient names={services.map((s) => s.name)} />;
}
