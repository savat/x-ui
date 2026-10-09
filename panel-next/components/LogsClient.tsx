"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet } from "@/lib/client";

export default function LogsClient({ names }: { names: string[] }) {
  const [name, setName] = useState(names[0] || "");
  const [lines, setLines] = useState(200);
  const [text, setText] = useState("");

  const load = useCallback(async () => {
    if (!name) return;
    try {
      const d = await apiGet<{ text: string }>(
        `/logs/${encodeURIComponent(name)}?lines=${lines}`,
      );
      setText(d.text);
    } catch (e) {
      setText((e as Error).message);
    }
  }, [name, lines]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <h1 className="page-title">บันทึกระบบ</h1>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <select className="input w-48" value={name} onChange={(e) => setName(e.target.value)}>
          {names.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <input
          className="input w-24"
          type="number"
          min={10}
          max={1000}
          value={lines}
          onChange={(e) => setLines(Number(e.target.value) || 200)}
        />
        <button className="btn" onClick={load}>
          รีเฟรช
        </button>
        <span className="text-xs text-slate-400">รหัสผ่าน / คีย์ / โทเคน ถูกปิดบัง</span>
      </div>
      <pre className="card max-h-[70vh] bg-ink-900/80 overflow-auto whitespace-pre-wrap break-all font-mono text-xs leading-relaxed text-slate-300">
        {text || "—"}
      </pre>
    </>
  );
}
