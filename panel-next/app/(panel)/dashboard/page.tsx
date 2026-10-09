import AutoRefresh from "@/components/AutoRefresh";
import Icon from "@/components/Icon";
import StatusBadge from "@/components/StatusBadge";
import { serverApi } from "@/lib/server";
import { fmtBytes, fmtUptime } from "@/lib/format";
import type { Dashboard } from "@/lib/types";

function Meter({ percent }: { percent: number }) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  const color =
    p >= 90 ? "from-rose-500 to-orange-400" : p >= 70 ? "from-amber-400 to-orange-400" : "from-violet-500 to-cyan-400";
  return (
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
      <div className={`h-full rounded-full bg-gradient-to-r ${color}`} style={{ width: `${p}%` }} />
    </div>
  );
}

function Stat({
  icon,
  title,
  value,
  sub,
  percent,
}: {
  icon: string;
  title: string;
  value: React.ReactNode;
  sub?: string;
  percent?: number;
}) {
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">{title}</span>
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-violet-500/15 text-violet-300">
          <Icon name={icon} className="h-4 w-4" />
        </span>
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {sub ? <div className="mt-1 text-xs text-slate-400">{sub}</div> : null}
      {percent !== undefined ? <Meter percent={percent} /> : null}
    </div>
  );
}

export default async function DashboardPage() {
  const d = await serverApi<Dashboard>("/dashboard");
  const uc = d.user_counts || {};
  const total = (uc.active || 0) + (uc.expired || 0) + (uc.disabled || 0);

  return (
    <>
      <AutoRefresh interval={10000} />
      <h1 className="page-title">
        ภาพรวมระบบ <small>อัปเดตอัตโนมัติทุก 10 วินาที</small>
      </h1>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          icon="cpu"
          title="ซีพียู"
          value={`${d.cpu_percent}%`}
          percent={d.cpu_percent}
          sub={`${d.cpus} คอร์ · โหลด ${d.load.map((x) => x.toFixed(2)).join(" ")}`}
        />
        <Stat
          icon="ram"
          title="หน่วยความจำ"
          value={`${d.memory.percent}%`}
          percent={d.memory.percent}
          sub={`${fmtBytes(d.memory.used)} / ${fmtBytes(d.memory.total)}`}
        />
        <Stat
          icon="disk"
          title="ดิสก์"
          value={`${d.disk.percent}%`}
          percent={d.disk.percent}
          sub={`${fmtBytes(d.disk.used)} / ${fmtBytes(d.disk.total)}`}
        />
        <Stat
          icon="clock"
          title="เวลาทำงาน"
          value={fmtUptime(d.uptime)}
          sub={`ไอพีสาธารณะ ${d.public_ip || "?"}`}
        />
        <Stat
          icon="wifi"
          title="ออนไลน์"
          value={d.online_users}
          sub={`${d.online_connections} การเชื่อมต่อ`}
        />
        <Stat
          icon="users"
          title="ผู้ใช้"
          value={`${uc.active || 0} ใช้งาน`}
          sub={`${uc.expired || 0} หมดอายุ · ${uc.disabled || 0} ปิดใช้งาน`}
          percent={total ? ((uc.active || 0) / total) * 100 : 0}
        />
        <div className="sm:col-span-2">
          <Stat
            icon="traffic"
            title="ทราฟฟิก (อินเทอร์เฟซ)"
            value={`↓ ${fmtBytes(d.traffic.rx_bytes)}  ↑ ${fmtBytes(d.traffic.tx_bytes)}`}
            sub="สะสมตั้งแต่เริ่มระบบ"
          />
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h2 className="card-title">
            <Icon name="zivpn" className="h-4 w-4 text-violet-300" /> ZIVPN
          </h2>
          <div className="space-y-2">
            {d.protocols.map((p) => (
              <div key={p.name} className="kv">
                <span className="text-sm text-slate-200">{p.label}</span>
                <StatusBadge state={p.state} />
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">
            <Icon name="services" className="h-4 w-4 text-violet-300" /> บริการ
          </h2>
          <div className="space-y-2">
            {d.services.map((s) => (
              <div key={s.name} className="kv">
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
