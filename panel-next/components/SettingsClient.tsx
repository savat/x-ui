"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useToast } from "./ToastProvider";
import { apiSend } from "@/lib/client";
import type { Audit, Settings } from "@/lib/types";

export default function SettingsClient({
  settings,
  audit,
}: {
  settings: Settings;
  audit: Audit[];
}) {
  const toast = useToast();
  const router = useRouter();
  const [host, setHost] = useState(settings.host);
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [busyHost, setBusyHost] = useState(false);
  const [busyPw, setBusyPw] = useState(false);

  async function saveHost() {
    setBusyHost(true);
    try {
      await apiSend("PUT", "/settings", { host });
      toast("บันทึกแล้ว");
      router.refresh();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusyHost(false);
    }
  }

  async function changePw() {
    setBusyPw(true);
    try {
      await apiSend("POST", "/auth/password", { current: cur, new: nw });
      toast("เปลี่ยนรหัสผ่านแล้ว");
      setCur("");
      setNw("");
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusyPw(false);
    }
  }

  return (
    <>
      <h1 className="page-title">ตั้งค่า</h1>

      <div className="space-y-4">
        <section className="card space-y-3">
          <h2 className="card-title mb-0">โฮสต์เซิร์ฟเวอร์ (ใช้ในคอนฟิกไคลเอนต์)</h2>
          <div className="flex gap-2">
            <input className="input" value={host} onChange={(e) => setHost(e.target.value)} />
            <button className="btn btn-primary" onClick={saveHost} disabled={busyHost}>
              บันทึก
            </button>
          </div>
          <p className="text-xs text-slate-400">ไอพีสาธารณะ: {settings.public_ip || "—"}</p>
        </section>

        <section className="card space-y-3">
          <h2 className="card-title mb-0">เปลี่ยนรหัสผ่านของฉัน (ขั้นต่ำ 10)</h2>
          <label className="block">
            <span className="label">รหัสผ่านปัจจุบัน</span>
            <input
              className="input"
              type="password"
              value={cur}
              onChange={(e) => setCur(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="label">รหัสผ่านใหม่</span>
            <input
              className="input"
              type="password"
              value={nw}
              onChange={(e) => setNw(e.target.value)}
            />
          </label>
          <button className="btn" onClick={changePw} disabled={busyPw}>
            เปลี่ยนรหัสผ่าน
          </button>
        </section>

        <section className="card">
          <h2 className="card-title">บันทึกกิจกรรม</h2>
          <div className="max-h-[60vh] space-y-1 overflow-auto font-mono text-xs">
            {audit.map((a, i) => (
              <div key={i} className="flex flex-wrap gap-x-3 border-b border-white/5 py-1 text-slate-400">
                <span className="text-slate-500">{a.created_at}</span>
                <span className="text-sky-300">{a.actor || "-"}</span>
                <span className="text-slate-200">{a.action}</span>
                <span className="text-slate-400">{a.detail || ""}</span>
                <span className="text-slate-500">{a.ip || ""}</span>
              </div>
            ))}
            {audit.length === 0 ? <div className="text-slate-500">—</div> : null}
          </div>
        </section>
      </div>
    </>
  );
}
