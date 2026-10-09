import { th, tone } from "@/lib/format";

export default function StatusBadge({ state, label }: { state?: string | null; label?: string }) {
  return <span className={`badge badge-${tone(state)}`}>{label ?? th(state)}</span>;
}
