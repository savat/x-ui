import Icon from "@/components/Icon";
import StatusBadge from "@/components/StatusBadge";
import { serverApi } from "@/lib/server";
import type { Protocol } from "@/lib/types";

const INFO_TH: Record<string, string> = {
  port: "พอร์ต UDP",
  obfs: "Obfs",
  port_range: "ช่วงพอร์ต (port hopping)",
};

export default async function ProtocolsPage() {
  const list = await serverApi<Protocol[]>("/protocols");
  const z = list.find((p) => p.name === "zivpn") ?? list[0];

  return (
    <>
      <h1 className="page-title">
        ZIVPN <small>เซิร์ฟเวอร์ UDP</small>
      </h1>

      {!z ? (
        <div className="card text-slate-400">ไม่พบข้อมูล ZIVPN</div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="card-title mb-0">
                <Icon name="zivpn" className="h-4 w-4 text-violet-300" /> {z.label}
              </h2>
              <StatusBadge state={z.state} />
            </div>
            <dl className="space-y-2">
              {Object.entries(z.info || {}).map(([k, v]) => (
                <div key={k} className="kv">
                  <dt>{INFO_TH[k] ?? k}</dt>
                  <dd>{String(v) || "—"}</dd>
                </div>
              ))}
            </dl>
            {!z.installed ? (
              <p className="mt-4 rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                ยังไม่ติดตั้ง — รันคำสั่ง: bash scripts/setup-zivpn.sh
              </p>
            ) : null}
          </div>

          <div className="card">
            <h2 className="card-title">
              <Icon name="services" className="h-4 w-4 text-violet-300" /> ยูนิตระบบ
            </h2>
            <div className="space-y-2">
              {Object.entries(z.units).map(([u, st]) => (
                <div key={u} className="kv">
                  <span className="font-mono text-xs text-slate-300">{u}</span>
                  <StatusBadge state={st} />
                </div>
              ))}
              {Object.keys(z.units).length === 0 ? (
                <p className="text-sm text-slate-500">—</p>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
