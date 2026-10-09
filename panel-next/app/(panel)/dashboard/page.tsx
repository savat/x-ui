import AutoRefresh from "@/components/AutoRefresh";
import StatusBadge from "@/components/StatusBadge";
import { serverApi } from "@/lib/server";
import { fmtBytes, fmtUptime } from "@/lib/format";
import type { Dashboard } from "@/lib/types";

function Stat({
  title,
  value,
  sub,
}: {
  title: string;
  value: React.ReactNode;
  sub?: string;
}) {
  return (
    <div className="card">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
        {title}
      </div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {sub ? <div className="mt-1 text-xs text-slate-400">{sub}</div> : null}
    </div>
  );
}

export default async function DashboardPage() {
  const d = await serverApi<Dashboard>("/dashboard");
  const uc = d.user_counts || {};

  return (
    <>
      <AutoRefresh interval={10000} />
      <h1 className="mb-5 text-xl font-semibold">ภาพรวมระบบ</h1>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          title="ซีพียู"
          value={`${d.cpu_percent}%`}
          sub={`${d.cpus} คอร์ · โหลด ${d.load.map((x) => x.toFixed(2)).join(" ")}`}
        />
        <Stat
          title="หน่วยความจำ"
          value={`${d.memory.percent}%`}
          sub={`${fmtBytes(d.memory.used)} / ${fmtBytes(d.memory.total)}`}
        />
        <Stat
          title="ดิสก์"
          value={`${d.disk.percent}%`}
          sub={`${fmtBytes(d.disk.used)} / ${fmtBytes(d.disk.total)}`}
        />
        <Stat title="เวลาทำงาน" value={fmtUptime(d.uptime)} sub={`ไอพีสาธารณะ ${d.public_ip || "?"}`} />
        <Stat
          title="ออนไลน์"
          value={d.online_users}
          sub={`${d.online_connections} การเชื่อมต่อ`}
        />
        <Stat
          title="ผู้ใช้"
          value={`${uc.active || 0} ใช้งาน`}
          sub={`${uc.expired || 0} หมดอายุ, ${uc.disabled || 0} ปิดใช้งาน`}
        />
        <Stat
          title="ทราฟฟิก (อินเทอร์เฟซ)"
          value={`↓ ${fmtBytes(d.traffic.rx_bytes)}`}
          sub={`↑ ${fmtBytes(d.traffic.tx_bytes)} ตั้งแต่เริ่มระบบ`}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h2 className="mb-3 font-semibold">โปรโตคอล</h2>
          <div className="space-y-2">
            {d.protocols.map((p) => (
              <div key={p.name} className="flex items-center justify-between rounded-lg bg-white/[0.02] px-3 py-2">
                <span className="text-sm">{p.label}</span>
                <StatusBadge state={p.state} />
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2 className="mb-3 font-semibold">บริการ</h2>
          <div className="space-y-2">
            {d.services.map((s) => (
              <div key={s.name} className="flex items-center justify-between rounded-lg bg-white/[0.02] px-3 py-2">
                <span className="font-mono text-xs text-slate-300">{s.unit}</span>
                <StatusBadge state={s.state} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
