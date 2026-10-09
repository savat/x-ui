import { redirect } from "next/navigation";
import AppShell from "@/components/AppShell";
import ToastProvider from "@/components/ToastProvider";
import { ApiError, serverApi } from "@/lib/server";
import type { Me } from "@/lib/types";

export const maxDuration = 60;

export default async function PanelLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let me: Me;
  try {
    me = await serverApi<Me>("/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) redirect("/login");
    throw e;
  }

  return (
    <ToastProvider>
      <AppShell me={me}>{children}</AppShell>
    </ToastProvider>
  );
}
