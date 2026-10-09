export type Role = "superadmin" | "admin" | "support" | string;

export type Me = {
  username: string;
  role: Role;
  csrf?: string;
};

export type User = {
  id: number;
  username: string;
  note?: string | null;
  status: string;
  protocols: string[];
  created_at?: string | null;
  expires_at?: string | null;
  max_connections?: number | null;
};

export type Protocol = {
  name: string;
  label: string;
  installed: boolean;
  state: string;
  units: Record<string, string>;
  info: Record<string, unknown>;
};

export type Service = {
  name: string;
  unit: string;
  state: string;
  protected?: boolean;
};

export type Backup = {
  name: string;
  size: number;
  mtime: number;
};

export type Audit = {
  id?: number;
  created_at: string;
  actor: string | null;
  action: string;
  detail: string | null;
  ip: string | null;
};

export type Settings = {
  host: string;
  public_ip: string;
  tls_selfsigned: boolean;
};

export type Dashboard = {
  cpu_percent: number;
  cpus: number;
  load: number[];
  memory: { total: number; used: number; percent: number };
  disk: { total: number; used: number; percent: number };
  uptime: number;
  traffic: { rx_bytes: number; tx_bytes: number; note?: string };
  public_ip?: string;
  host?: string;
  online_users: number;
  online_connections: number;
  user_counts: Record<string, number>;
  protocols: { name: string; label: string; state: string }[];
  services: Service[];
};

export type ShareItem = {
  protocol: string;
  account_status: string;
  info: Record<string, unknown>;
};

export const PROTOCOLS = ["zivpn"] as const;
