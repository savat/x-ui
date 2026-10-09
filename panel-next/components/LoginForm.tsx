"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Icon from "./Icon";
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
    <div className="relative grid min-h-screen place-items-center overflow-hidden p-6">
      <div className="pointer-events-none absolute -left-24 top-1/4 h-72 w-72 rounded-full bg-violet-600/25 blur-3xl" />
      <div className="pointer-events-none absolute -right-24 bottom-1/4 h-72 w-72 rounded-full bg-cyan-500/20 blur-3xl" />

      <form onSubmit={go} className="card page w-full max-w-sm space-y-5 p-8">
        <div className="text-center">
          <span className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-3xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-xl shadow-violet-900/50">
            <Icon name="zivpn" className="h-8 w-8" />
          </span>
          <h1 className="text-xl font-semibold tracking-tight">ZIVPN Panel</h1>
          <p className="mt-1 text-sm text-slate-400">เข้าสู่ระบบเพื่อจัดการแผงควบคุม</p>
        </div>

        <label className="block">
          <span className="label">ชื่อผู้ใช้</span>
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>

        <label className="block">
          <span className="label">รหัสผ่าน</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {err ? (
          <p className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {err}
          </p>
        ) : null}

        <button className="btn btn-primary w-full py-2.5" disabled={busy}>
          {busy ? "กำลังเข้าสู่ระบบ…" : "เข้าสู่ระบบ"}
        </button>
      </form>
    </div>
  );
}
