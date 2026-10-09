"use client";

import { useState } from "react";
import { apiSend } from "@/lib/client";
import { useToast } from "./ToastProvider";

export default function RestoreBackupButton({ name }: { name: string }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function run() {
    const v = window.prompt(
      "พิมพ์ชื่อไฟล์สำรองเพื่อยืนยันการกู้คืน (จะเขียนทับข้อมูลปัจจุบัน):",
    );
    if (v !== name) return;
    setBusy(true);
    try {
      await apiSend("POST", `/backups/${encodeURIComponent(name)}/restore`, {
        confirm: name,
      });
      toast("เริ่มกู้คืนแล้ว แผงควบคุมจะรีสตาร์ท");
      setTimeout(() => window.location.reload(), 4000);
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className="btn btn-sm" onClick={run} disabled={busy}>
      กู้คืน
    </button>
  );
}
