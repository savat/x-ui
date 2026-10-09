"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiSend, setCsrf } from "@/lib/client";

export default function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const d = await apiSend<{ csrf: string }>("POST", "/auth/login", { username, password });
      setCsrf(d.csrf);
      router.replace("/dashboard");
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center p-6">
      <form onSubmit={go} className="card w-full max-w-sm space-y-4 p-8">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-b from-sky-400 to-sky-600 text-lg font-bold text-white shadow-lg shadow-sky-900/40">
            UV
          </span>
          <div>
            <h1 className="text-lg font-semibold">Unified VPN</h1>
            <p className="text-xs text-slate-400">เข้าสู่ระบบเพื่อจัดการแผงควบคุม</p>
          </div>
        </div>

        <label className="block space-y-1.5">
          <span className="text-sm text-slate-300">ชื่อผู้ใช้</span>
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-sm text-slate-300">รหัสผ่าน</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {err ? <p className="text-sm text-rose-400">{err}</p> : null}

        <button className="btn btn-primary w-full py-2.5" disabled={busy}>
          {busy ? "กำลังเข้าสู่ระบบ…" : "เข้าสู่ระบบ"}
        </button>
      </form>
    </div>
  );
}
