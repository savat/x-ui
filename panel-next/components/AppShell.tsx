"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { apiSend } from "@/lib/client";
import { roleTh } from "@/lib/format";
import type { Me } from "@/lib/types";

const TABS = [
  { id: "dashboard", th: "ภาพรวม", icon: "▦" },
  { id: "users", th: "ผู้ใช้", icon: "☰" },
  { id: "protocols", th: "โปรโตคอล", icon: "⇄" },
  { id: "services", th: "บริการ", icon: "⚙" },
  { id: "logs", th: "บันทึกระบบ", icon: "▤" },
  { id: "backups", th: "สำรองข้อมูล", icon: "⛁" },
  { id: "settings", th: "ตั้งค่า", icon: "✱" },
];

export default function AppShell({
  me,
  children,
}: {
  me: Me;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function logout() {
    setBusy(true);
    try {
      await apiSend("POST", "/auth/logout", {});
      router.replace("/login");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col gap-6 border-b border-white/5 bg-white/[0.02] p-4 md:h-screen md:w-64 md:border-b-0 md:border-r md:p-5 md:sticky md:top-0">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-b from-sky-400 to-sky-600 font-bold text-white shadow-lg shadow-sky-900/40">
            UV
          </span>
          <div>
            <b className="block leading-tight">Unified VPN</b>
            <small className="text-xs text-slate-400">แผงควบคุม</small>
          </div>
        </div>

        <nav className="flex flex-row gap-1 overflow-x-auto md:flex-col">
          {TABS.map((t) => {
            const on = pathname === `/${t.id}`;
            return (
              <Link
                key={t.id}
                href={`/${t.id}`}
                className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  on
                    ? "bg-sky-500/15 text-sky-300"
                    : "text-slate-300 hover:bg-white/5 hover:text-white"
                }`}
              >
                <span className="text-base opacity-80">{t.icon}</span>
                {t.th}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.03] p-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink-700 text-sm font-semibold">
            {(me.username || "?").charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <b className="block truncate text-sm">{me.username}</b>
            <small className="text-xs text-slate-400">{roleTh(me.role)}</small>
          </div>
          <button className="btn px-2 py-1 text-xs" onClick={logout} disabled={busy}>
            ออก
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 p-4 md:h-screen md:overflow-y-auto md:p-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
