"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ensureCsrf } from "@/lib/client";

type Toast = { id: number; msg: string; bad?: boolean };

const Ctx = createContext<(msg: string, bad?: boolean) => void>(() => {});

export function useToast() {
  return useContext(Ctx);
}

export default function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);

  useEffect(() => {
    ensureCsrf();
  }, []);

  const push = useCallback((msg: string, bad?: boolean) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, msg, bad }]);
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 3500);
  }, []);

  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-50 flex flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto rounded-xl border px-4 py-2.5 text-sm shadow-xl backdrop-blur ${
              t.bad
                ? "border-rose-500/30 bg-rose-950/85 text-rose-100"
                : "border-emerald-500/30 bg-emerald-950/85 text-emerald-100"
            }`}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
