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
      <h1 className="page-title">บริการระบบ <small>รีเฟรชทุก 15 วินาที</small></h1>
      <div className="table-wrap">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th>ยูนิต</th>
              <th>สถานะ</th>
              <th>การจัดการ</th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => {
              return (
                <tr key={s.name}>
                  <td className="font-mono text-xs text-slate-200">{s.unit}</td>
                  <td >
                    <StatusBadge state={s.state} />
                  </td>
                  <td >
                    <div className="flex flex-wrap gap-1.5">
                      <ActionButton
                        className="btn btn-sm"
                        path={`/services/${s.name}/start`}
                        confirmText={`เริ่ม ${s.name} ?`}
                        disabled={!!s.protected}
                      >
                        เริ่ม
                      </ActionButton>
                      <ActionButton
                        className="btn btn-sm"
                        path={`/services/${s.name}/stop`}
                        confirmText={`หยุด ${s.name} ?`}
                        disabled={!!s.protected}
                      >
                        หยุด
                      </ActionButton>
                      <ActionButton
                        className="btn btn-sm"
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
