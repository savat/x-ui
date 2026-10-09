const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"];

export function fmtBytes(input: number): string {
  let n = Number(input) || 0;
  let i = 0;
  while (n >= 1024 && i < BYTE_UNITS.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${BYTE_UNITS[i]}`;
}

export function fmtTime(s?: string | null): string {
  if (!s) return "–";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleString("th-TH");
}

export function fmtUptime(seconds: number): string {
  const s = Number(seconds) || 0;
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${d} วัน ${h} ชม. ${m} นาที`;
}

export function roleTh(role?: string | null): string {
  if (role === "superadmin") return "ผู้ดูแลระบบสูงสุด";
  if (role === "admin") return "ผู้ดูแลระบบ";
  if (role === "support") return "ผู้ช่วยเหลือ";
  return role || "";
}

const STATUS_TH: Record<string, string> = {
  RUNNING: "ทำงาน",
  ACTIVE: "ใช้งาน",
  STOPPED: "หยุด",
  DISABLED: "ปิดใช้งาน",
  INACTIVE: "ไม่ทำงาน",
  ERROR: "ผิดพลาด",
  EXPIRED: "หมดอายุ",
  FAILED: "ล้มเหลว",
  UNKNOWN: "ไม่ทราบ",
  NOT_INSTALLED: "ยังไม่ติดตั้ง",
};

export function th(state?: string | null): string {
  if (!state) return "";
  return STATUS_TH[state.toUpperCase()] || String(state);
}

export function tone(state?: string | null): "ok" | "bad" | "warn" | "neutral" {
  const u = String(state || "").toUpperCase();
  if (/ERROR|FAIL|EXPIRED/.test(u)) return "bad";
  if (/NOT_INSTALLED|STOP|DISABL|INACTIVE/.test(u)) return "warn";
  if (/RUNNING|ACTIVE|OK|UP/.test(u)) return "ok";
  return "neutral";
}
