"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ActionButton from "./ActionButton";
import Icon from "./Icon";
import StatusBadge from "./StatusBadge";
import { useToast } from "./ToastProvider";
import { apiGet, apiSend } from "@/lib/client";
import { fmtTime } from "@/lib/format";
import type { ShareItem, User } from "@/lib/types";

const INFO_TH: Record<string, string> = {
  server: "เซิร์ฟเวอร์",
  port: "พอร์ต",
  obfs: "Obfs",
  password: "รหัสผ่าน",
  port_range: "ช่วงพอร์ต",
};

export default function UsersClient({ initial }: { initial: User[] }) {
  const toast = useToast();
  const [list, setList] = useState<User[]>(initial);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [configUser, setConfigUser] = useState<User | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      setList(await apiGet<User[]>(`/users?q=${encodeURIComponent(q)}&status=${status}`));
    } catch (e) {
      toast((e as Error).message, true);
    }
  }, [q, status, toast]);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(load, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [load]);

  return (
    <>
      <h1 className="page-title">
        จัดการผู้ใช้ <small>{list.length} บัญชี</small>
      </h1>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Icon
            name="search"
            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
          />
          <input
            className="input pl-10"
            placeholder="ค้นหาชื่อหรือหมายเหตุ…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select className="input w-40" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">ทุกสถานะ</option>
          <option value="active">ใช้งาน</option>
          <option value="expired">หมดอายุ</option>
          <option value="disabled">ปิดใช้งาน</option>
        </select>
        <button className="btn btn-primary ml-auto" onClick={() => setAddOpen(true)}>
          <Icon name="plus" /> เพิ่มผู้ใช้
        </button>
      </div>

      <div className="table-wrap">
        <table className="w-full text-sm">
          <thead>
            <tr>
              {["ผู้ใช้", "สร้างเมื่อ", "หมดอายุ", "การเชื่อมต่อสูงสุด", "สถานะ", "การจัดการ"].map((t) => (
                <th key={t}>{t}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list.map((u) => (
              <tr key={u.id}>
                <td>
                  <div className="flex items-center gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500/30 to-cyan-500/20 text-sm font-semibold ring-1 ring-white/10">
                      {u.username.charAt(0).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <b className="block truncate">{u.username}</b>
                      {u.note ? <span className="text-xs text-slate-400">{u.note}</span> : null}
                    </div>
                  </div>
                </td>
                <td className="whitespace-nowrap text-xs text-slate-400">{fmtTime(u.created_at)}</td>
                <td className="whitespace-nowrap text-xs text-slate-400">{fmtTime(u.expires_at)}</td>
                <td>{u.max_connections || "ไม่จำกัด"}</td>
                <td>
                  <StatusBadge state={u.status} />
                </td>
                <td>
                  <div className="flex flex-wrap gap-1.5">
                    <button className="btn btn-sm" onClick={() => setConfigUser(u)}>
                      ข้อมูลเชื่อมต่อ
                    </button>
                    <ActionButton
                      path={`/users/${u.id}/renew`}
                      prompt={{ label: "ต่ออายุเพิ่มกี่วัน?", field: "days", initial: "30" }}
                      onDone={load}
                    >
                      ต่ออายุ
                    </ActionButton>
                    {u.status === "active" ? (
                      <ActionButton path={`/users/${u.id}/disable`} onDone={load}>
                        ปิดใช้งาน
                      </ActionButton>
                    ) : (
                      <ActionButton path={`/users/${u.id}/enable`} onDone={load}>
                        เปิดใช้งาน
                      </ActionButton>
                    )}
                    <ActionButton
                      path={`/users/${u.id}/reset-password`}
                      prompt={{ label: "รหัสผ่านใหม่", field: "password" }}
                      onDone={load}
                      okMsg="อัปเดตรหัสผ่านแล้ว"
                    >
                      รหัสผ่าน
                    </ActionButton>
                    <ActionButton
                      method="PUT"
                      path={`/users/${u.id}`}
                      prompt={{
                        label: "จำนวนการเชื่อมต่อสูงสุด (0 = ไม่จำกัด)",
                        field: "max_connections",
                        initial: String(u.max_connections ?? 0),
                      }}
                      onDone={load}
                    >
                      จำกัด
                    </ActionButton>
                    <ActionButton
                      className="btn btn-sm btn-danger"
                      method="DELETE"
                      path={`/users/${u.id}`}
                      confirmText={`ลบผู้ใช้ ${u.username} ?`}
                      onDone={load}
                      okMsg="ลบผู้ใช้แล้ว"
                    >
                      ลบ
                    </ActionButton>
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-14 text-center text-slate-400">
                  ไม่พบผู้ใช้
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {addOpen ? (
        <AddUserDialog
          onClose={() => setAddOpen(false)}
          onDone={() => {
            setAddOpen(false);
            load();
          }}
        />
      ) : null}

      {configUser ? <ConfigDialog user={configUser} onClose={() => setConfigUser(null)} /> : null}
    </>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/65 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="card max-h-[88vh] w-full max-w-lg overflow-y-auto bg-ink-850 shadow-2xl"
        style={{ animation: "pop 0.2s ease both" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          <button className="btn btn-sm" onClick={onClose}>
            ปิด
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function AddUserDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [days, setDays] = useState("30");
  const [maxConn, setMaxConn] = useState("1");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await apiSend("POST", "/users", {
        username,
        password,
        days,
        max_connections: maxConn,
        note,
        protocols: ["zivpn"],
      });
      toast("สร้างผู้ใช้แล้ว");
      onDone();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="เพิ่มผู้ใช้ ZIVPN" onClose={onClose}>
      <div className="grid gap-4 sm:grid-cols-2">
        <label>
          <span className="label">ชื่อผู้ใช้</span>
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          <span className="label">รหัสผ่าน (ใช้เชื่อมต่อใน ZIVPN)</span>
          <input className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label>
          <span className="label">จำนวนวัน</span>
          <input
            className="input"
            type="number"
            min={1}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </label>
        <label>
          <span className="label">การเชื่อมต่อสูงสุด (0 = ไม่จำกัด)</span>
          <input
            className="input"
            type="number"
            min={0}
            value={maxConn}
            onChange={(e) => setMaxConn(e.target.value)}
          />
        </label>
        <label className="sm:col-span-2">
          <span className="label">หมายเหตุ</span>
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <button className="btn" onClick={onClose}>
          ยกเลิก
        </button>
        <button className="btn btn-primary" onClick={submit} disabled={busy}>
          สร้าง
        </button>
      </div>
    </Modal>
  );
}

function ConfigDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const toast = useToast();
  const [items, setItems] = useState<ShareItem[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiGet<ShareItem[]>(`/users/${user.id}/share`)
      .then(setItems)
      .catch((e) => setErr((e as Error).message));
  }, [user.id]);

  function copy(text: string, msg = "คัดลอกแล้ว") {
    navigator.clipboard?.writeText(text);
    toast(msg);
  }

  return (
    <Modal title={`ข้อมูลเชื่อมต่อ: ${user.username}`} onClose={onClose}>
      {err ? <p className="text-rose-400">{err}</p> : null}
      {!items && !err ? <p className="text-slate-400">กำลังโหลด…</p> : null}
      <div className="space-y-4">
        {items?.map((it) => {
          const info = Object.entries(it.info || {}).filter(([k]) => k !== "note");
          return (
            <div key={it.protocol} className="space-y-3">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold uppercase tracking-wide">{it.protocol}</h3>
                <StatusBadge state={it.account_status} />
              </div>
              <dl className="space-y-2">
                {info.map(([k, v]) => (
                  <div key={k} className="kv">
                    <dt>{INFO_TH[k] ?? k}</dt>
                    <dd className="flex-1 text-right">{String(v)}</dd>
                    <button
                      className="btn btn-sm"
                      onClick={() => copy(String(v))}
                      aria-label="คัดลอก"
                    >
                      <Icon name="copy" className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </dl>
              <button
                className="btn btn-primary w-full"
                onClick={() =>
                  copy(
                    info.map(([k, v]) => `${INFO_TH[k] ?? k}: ${String(v)}`).join("\n"),
                    "คัดลอกข้อมูลทั้งหมดแล้ว",
                  )
                }
              >
                <Icon name="copy" /> คัดลอกทั้งหมดส่งให้ลูกค้า
              </button>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
