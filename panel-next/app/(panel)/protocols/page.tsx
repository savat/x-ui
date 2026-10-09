import StatusBadge from "@/components/StatusBadge";
import { serverApi } from "@/lib/server";
import type { Protocol } from "@/lib/types";

export default async function ProtocolsPage() {
  const list = await serverApi<Protocol[]>("/protocols");
  return (
    <>
      <h1 className="mb-5 text-xl font-semibold">โปรโตคอล</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {list.map((p) => (
          <div key={p.name} className="card">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{p.label}</h2>
              <StatusBadge state={p.state} />
            </div>

            {Object.keys(p.info || {}).length > 0 ? (
              <div className="mt-2 break-all text-xs text-slate-400">
                {JSON.stringify(p.info)}
              </div>
            ) : null}

            <div className="mt-3 space-y-1">
              {Object.entries(p.units).map(([u, st]) => (
                <div
                  key={u}
                  className="flex items-center justify-between rounded-lg bg-white/[0.02] px-3 py-1.5"
                >
                  <span className="font-mono text-xs text-slate-300">{u}</span>
                  <StatusBadge state={st} />
                </div>
              ))}
            </div>

            {!p.installed ? (
              <p className="mt-3 text-xs text-amber-300">
                ยังไม่ติดตั้ง — รันคำสั่ง: unified-vpn adapter-install {p.name}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </>
  );
}
