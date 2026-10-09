"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiSend } from "@/lib/client";
import { useToast } from "./ToastProvider";

type Props = {
  method?: "POST" | "PUT" | "DELETE";
  path: string;
  body?: unknown;
  children: React.ReactNode;
  confirmText?: string;
  prompt?: { label: string; field: string; initial?: string };
  okMsg?: string;
  className?: string;
  disabled?: boolean;
  onDone?: () => void;
};

export default function ActionButton({
  method = "POST",
  path,
  body,
  children,
  confirmText,
  prompt,
  okMsg,
  className = "btn btn-sm",
  disabled,
  onDone,
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function run() {
    if (confirmText && !window.confirm(confirmText)) return;
    let payload: unknown = body;
    if (prompt) {
      const v = window.prompt(prompt.label, prompt.initial ?? "");
      if (v === null) return;
      payload = { ...(body as object | undefined), [prompt.field]: v };
    }
    setBusy(true);
    try {
      await apiSend(method, path, payload ?? {});
      toast(okMsg || "สำเร็จ");
      onDone?.();
      router.refresh();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className={className} onClick={run} disabled={disabled || busy}>
      {children}
    </button>
  );
}
