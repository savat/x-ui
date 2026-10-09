"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ActionButton from "./ActionButton";
import StatusBadge from "./StatusBadge";
import { useToast } from "./ToastProvider";
import { apiGet, apiSend } from "@/lib/client";
import { fmtTime } from "@/lib/format";
import { PROTOCOLS, type ShareItem, type User } from "@/lib/types";

export default function UsersClient({ initial }: { initial: User[] }) {
  const toast = useToast();
  const [list, setList] = useState<User[]>(initial);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [protocol, setProtocol] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [configUser, setConfigUser] = useState<User | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const url = `/users?q=${encodeURIComponent(q)}&status=${status}&protocol=${protocol}`;
      setList(await apiGet<User[]>(url));
    } catch (e) {
      toast((e as Error).message, true);
    }
  }, [q, status, protocol, toast]);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(load, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [load]);

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">จัดการผู้ใช้</h1>
        <input
          className="input w-44"
          placeholder="ค้นหา…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="input w-32" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">ทุกสถานะ</option>
          <option value="active">ใช้งาน</option>
          <option value="expired">หมดอายุ</option>
          <option value="disabled">ปิดใช้งาน</option>
        </select>
        <select
          className="input w-36"
          value={protocol}
          onChange={(e) => setProtocol(e.target.value)}
        >
          <option value="">ทุกโปรโตคอล</option>
          {PROTOCOLS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <button className="btn btn-primary" onClick={() => setAddOpen(true)}>
          เพิ่มผู้ใช้
        </button>
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              {["ID", "ผู้ใช้", "โปรโตคอล", "สร้างเมื่อ", "หมดอายุ", "อุปกรณ์สูงสุด", "สถานะ", "การจัดการ"].map(
                (t) => (
                  <th key={t} className="whitespace-nowrap px-4 py-3 font-medium">
                    {t}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {list.map((u) => (
              <tr key={u.id} className="border-t border-white/5 hover:bg-white/[0.02]">
                <td className="px-4 py-3 text-slate-400">{u.id}</td>
                <td className="px-4 py-3">
                  <b className="block">{u.username}</b>
                  {u.note ? <span className="text-xs text-slate-400">{u.note}</span> : null}
                </td>
                <td className="px-4 py-3 text-xs text-slate-300">{u.protocols.join(", ")}</td>
                <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                  {fmtTime(u.created_at)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                  {fmtTime(u.expires_at)}
                </td>
                <td className="px-4 py-3">
                  {u.max_connections || "ไม่จำกัด"}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge state={u.status} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1.5">
                    <button className="btn px-2 py-1 text-xs" onClick={() => setConfigUser(u)}>
                      คอนฟิก
                    </button>
                    <ActionButton
                      className="btn px-2 py-1 text-xs"
                      path={`/users/${u.id}/renew`}
                      prompt={{ label: "ต่ออายุเพิ่มกี่วัน?", field: "days", initial: "30" }}
                      onDone={load}
                    >
                      ต่ออายุ
                    </ActionButton>
                    {u.status === "active" ? (
                      <ActionButton
                        className="btn px-2 py-1 text-xs"
                        path={`/users/${u.id}/disable`}
                        onDone={load}
                      >
                        ปิดใช้งาน
                      </ActionButton>
                    ) : (
                      <ActionButton
                        className="btn px-2 py-1 text-xs"
                        path={`/users/${u.id}/enable`}
                        onDone={load}
                      >
                        เปิดใช้งาน
                      </ActionButton>
                    )}
                    <ActionButton
                      className="btn px-2 py-1 text-xs"
                      path={`/users/${u.id}/reset-password`}
                      prompt={{ label: "รหัสผ่านใหม่", field: "password" }}
                      onDone={load}
                      okMsg="อัปเดตรหัสผ่านแล้ว"
                    >
                      รหัสผ่าน
                    </ActionButton>
                    <ActionButton
                      className="btn px-2 py-1 text-xs"
                      method="PUT"
                      path={`/users/${u.id}`}
                      prompt={{
                        label: "จำนวนอุปกรณ์สูงสุด (0 = ไม่จำกัด)",
                        field: "max_connections",
                        initial: String(u.max_connections ?? 0),
                      }}
                      onDone={load}
                    >
                      จำกัด
                    </ActionButton>
                    <ActionButton
                      className="btn btn-danger px-2 py-1 text-xs"
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
                <td colSpan={8} className="px-4 py-10 text-center text-slate-400">
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

      {configUser ? (
        <ConfigDialog user={configUser} onClose={() => setConfigUser(null)} />
      ) : null}
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
      className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="card max-h-[85vh] w-full max-w-xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button className="btn px-2 py-1" onClick={onClose}>
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
  const [protos, setProtos] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  function toggle(p: string) {
    setProtos((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]));
  }

  async function submit() {
    setBusy(true);
    try {
      await apiSend("POST", "/users", {
        username,
        password,
        days,
        max_connections: maxConn,
        note,
        protocols: protos,
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
    <Modal title="เพิ่มผู้ใช้" onClose={onClose}>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1.5">
          <span className="text-sm text-slate-300">ชื่อผู้ใช้</span>
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm text-slate-300">รหัสผ่าน</span>
          <input className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm text-slate-300">จำนวนวัน</span>
          <input
            className="input"
            type="number"
            min={1}
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm text-slate-300">อุปกรณ์สูงสุด (0 = ไม่จำกัด)</span>
          <input
            className="input"
            type="number"
            min={0}
            value={maxConn}
            onChange={(e) => setMaxConn(e.target.value)}
          />
        </label>
        <label className="space-y-1.5 sm:col-span-2">
          <span className="text-sm text-slate-300">หมายเหตุ</span>
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      </div>

      <div className="mt-4">
        <span className="text-sm text-slate-300">โปรโตคอล</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {PROTOCOLS.map((p) => (
            <label
              key={p}
              className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm transition ${
                protos.includes(p)
                  ? "border-sky-500/50 bg-sky-500/15 text-sky-200"
                  : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
              }`}
            >
              <input
                type="checkbox"
                className="hidden"
                checked={protos.includes(p)}
                onChange={() => toggle(p)}
              />
              {p}
            </label>
          ))}
        </div>
      </div>

      <div className="mt-5 flex justify-end gap-2">
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

  function copy(url: string) {
    navigator.clipboard?.writeText(url);
    toast("คัดลอกลิงก์แล้ว");
  }

  return (
    <Modal title={`คอนฟิก: ${user.username}`} onClose={onClose}>
      {err ? <p className="text-rose-400">{err}</p> : null}
      {!items && !err ? <p className="text-slate-400">กำลังโหลด…</p> : null}
      <div className="space-y-4">
        {items?.map((it) => (
          <div key={it.protocol} className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="font-semibold uppercase">{it.protocol}</h3>
              <StatusBadge state={it.account_status} />
            </div>

            {it.links.map((l, i) => (
              <div key={i} className="mb-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-lg bg-ink-900/80 px-3 py-2 text-xs text-sky-200">
                  {l.url}
                </code>
                <button className="btn px-2 py-1 text-xs" onClick={() => copy(l.url)}>
                  คัดลอก
                </button>
              </div>
            ))}

            {it.links.length > 0 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                className="mx-auto my-2 h-40 w-40 rounded-xl bg-white p-2"
                alt="QR"
                src={`/api/users/${user.id}/qr?protocol=${it.protocol}`}
              />
            ) : null}

            {it.files.map((f) => (
              <div key={f.label} className="mb-1">
                <a
                  className="text-sm text-sky-300 underline"
                  href={`/api/users/${user.id}/config?protocol=${f.protocol}&proto=${f.proto || ""}`}
                >
                  ดาวน์โหลด {f.label}
                </a>
              </div>
            ))}

            {it.files.some((f) => f.protocol === "wireguard") ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                className="mx-auto my-2 h-40 w-40 rounded-xl bg-white p-2"
                alt="QR"
                src={`/api/users/${user.id}/qr?protocol=wireguard`}
              />
            ) : null}

            {Object.keys(it.info || {}).length > 0 ? (
              <dl className="mt-2 space-y-1 text-xs text-slate-400">
                {Object.entries(it.info).map(([k, v]) => (
                  <div key={k} className="flex gap-2">
                    <dt className="text-slate-500">{k}:</dt>
                    <dd className="text-slate-300">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </div>
        ))}
      </div>
    </Modal>
  );
}
