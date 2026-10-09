import ActionButton from "@/components/ActionButton";
import RestoreBackupButton from "@/components/RestoreBackupButton";
import { serverApi } from "@/lib/server";
import { fmtBytes } from "@/lib/format";
import type { Backup } from "@/lib/types";

export default async function BackupsPage() {
  const list = await serverApi<Backup[]>("/backups");
  return (
    <>
      <h1 className="page-title">สำรองข้อมูล</h1>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <ActionButton
          className="btn btn-primary"
          path="/backups"
          okMsg="สร้างข้อมูลสำรองแล้ว"
        >
          สร้างข้อมูลสำรอง
        </ActionButton>
        <span className="text-xs text-slate-400">
          เข้ารหัสด้วยคีย์ที่ /opt/unified-vpn/config/backup.key — เก็บคีย์นี้ไว้ให้ปลอดภัย
        </span>
      </div>

      <div className="table-wrap">
        <table className="w-full text-sm">
          <thead>
            <tr>
              {["ชื่อไฟล์", "ขนาด", "เวลา", "การจัดการ"].map((t) => (
                <th key={t}>
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list.map((b) => (
              <tr key={b.name}>
                <td className="font-mono text-xs text-slate-200">{b.name}</td>
                <td className="text-slate-300">{fmtBytes(b.size)}</td>
                <td className="whitespace-nowrap text-xs text-slate-400">
                  {new Date(b.mtime * 1000).toLocaleString("th-TH")}
                </td>
                <td >
                  <div className="flex flex-wrap gap-1.5">
                    <a
                      className="btn btn-sm"
                      href={`/api/backups/${encodeURIComponent(b.name)}`}
                    >
                      ดาวน์โหลด
                    </a>
                    <RestoreBackupButton name={b.name} />
                    <ActionButton
                      className="btn btn-sm btn-danger"
                      method="DELETE"
                      path={`/backups/${encodeURIComponent(b.name)}`}
                      confirmText="ลบข้อมูลสำรองนี้?"
                      okMsg="ลบข้อมูลสำรองแล้ว"
                    >
                      ลบ
                    </ActionButton>
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-slate-400">
                  ยังไม่มีข้อมูลสำรอง
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </>
  );
}
