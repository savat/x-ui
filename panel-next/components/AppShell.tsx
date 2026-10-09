"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import Icon from "./Icon";
import { apiSend } from "@/lib/client";
import { roleTh } from "@/lib/format";
import type { Me } from "@/lib/types";

const TABS = [
  { id: "dashboard", th: "ภาพรวม", icon: "dashboard" },
  { id: "users", th: "ผู้ใช้", icon: "users" },
  { id: "protocols", th: "ZIVPN", icon: "zivpn" },
  { id: "services", th: "บริการ", icon: "services" },
  { id: "logs", th: "บันทึกระบบ", icon: "logs" },
  { id: "backups", th: "สำรองข้อมูล", icon: "backups" },
  { id: "settings", th: "ตั้งค่า", icon: "settings" },
];

export default function AppShell({ me, children }: { me: Me; children: React.ReactNode }) {
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
      <aside className="sticky top-0 z-30 flex shrink-0 flex-col gap-5 border-b border-white/[0.06] bg-ink-950/70 p-4 backdrop-blur-xl md:h-screen md:w-64 md:border-b-0 md:border-r md:p-5">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-lg shadow-violet-900/50">
            <Icon name="zivpn" className="h-6 w-6" />
          </span>
          <div className="flex-1">
            <b className="block text-base leading-tight tracking-tight">ZIVPN Panel</b>
            <small className="text-xs text-slate-400">แผงควบคุม UDP</small>
          </div>
          <button
            className="btn btn-sm md:hidden"
            onClick={logout}
            disabled={busy}
            aria-label="ออกจากระบบ"
          >
            <Icon name="logout" />
          </button>
        </div>

        <nav className="-mx-1 flex flex-row gap-1 overflow-x-auto px-1 pb-1 md:mx-0 md:flex-col md:overflow-visible md:px-0 md:pb-0">
          {TABS.map((t) => {
            const on = pathname === `/${t.id}`;
            return (
              <Link
                key={t.id}
                href={`/${t.id}`}
                className={`group relative flex shrink-0 items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                  on
                    ? "bg-gradient-to-r from-violet-500/20 to-fuchsia-500/10 text-white ring-1 ring-violet-400/25"
                    : "text-slate-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                {on ? (
                  <span className="absolute -left-px top-2 hidden h-6 w-1 rounded-full bg-gradient-to-b from-violet-400 to-fuchsia-400 md:block" />
                ) : null}
                <Icon
                  name={t.icon}
                  className={`h-[18px] w-[18px] ${on ? "text-violet-300" : "opacity-70 group-hover:opacity-100"}`}
                />
                {t.th}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto hidden items-center gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.03] p-3 md:flex">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500/30 to-cyan-500/30 text-sm font-semibold ring-1 ring-white/10">
            {(me.username || "?").charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <b className="block truncate text-sm">{me.username}</b>
            <small className="text-xs text-slate-400">{roleTh(me.role)}</small>
          </div>
          <button
            className="btn btn-sm"
            onClick={logout}
            disabled={busy}
            aria-label="ออกจากระบบ"
            title="ออกจากระบบ"
          >
            <Icon name="logout" />
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 p-4 md:h-screen md:overflow-y-auto md:p-8">
        <div className="page mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
