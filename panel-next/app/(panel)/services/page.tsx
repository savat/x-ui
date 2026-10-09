import ActionButton from "@/components/ActionButton";
import AutoRefresh from "@/components/AutoRefresh";
import StatusBadge from "@/components/StatusBadge";
import { serverApi } from "@/lib/server";
import type { Service } from "@/lib/types";

export default async function ServicesPage() {
  const list = await serverApi<Service[]>("/services");
  return (
    <>
      <AutoRefresh interval={15000} />
      <h1 className="mb-5 text-xl font-semibold">บริการระบบ</h1>
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="px-4 py-3 font-medium">ยูนิต</th>
              <th className="px-4 py-3 font-medium">สถานะ</th>
              <th className="px-4 py-3 font-medium">การจัดการ</th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => {
              return (
                <tr key={s.name} className="border-t border-white/5 hover:bg-white/[0.02]">
                  <td className="px-4 py-3 font-mono text-xs text-slate-200">{s.unit}</td>
                  <td className="px-4 py-3">
                    <StatusBadge state={s.state} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      <ActionButton
                        className="btn px-2 py-1 text-xs"
                        path={`/services/${s.name}/start`}
                        confirmText={`เริ่ม ${s.name} ?`}
                        disabled={!!s.protected}
                      >
                        เริ่ม
                      </ActionButton>
                      <ActionButton
                        className="btn px-2 py-1 text-xs"
                        path={`/services/${s.name}/stop`}
                        confirmText={`หยุด ${s.name} ?`}
                        disabled={!!s.protected}
                      >
                        หยุด
                      </ActionButton>
                      <ActionButton
                        className="btn px-2 py-1 text-xs"
                        path={`/services/${s.name}/restart`}
                        confirmText={`รีสตาร์ท ${s.name} ?`}
                      >
                        รีสตาร์ท
                      </ActionButton>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
