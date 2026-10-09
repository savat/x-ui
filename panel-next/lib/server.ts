import { cookies } from "next/headers";

const API_BASE = process.env.UVPN_API_BASE || "http://127.0.0.1:8080";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function serverApi<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieHeader = (await cookies()).toString();

  const headers = new Headers(init?.headers);
  if (cookieHeader) headers.set("cookie", cookieHeader);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const res = await fetch(`${API_BASE}/api${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  const text = await res.text();
  let data: unknown = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text };
    }
  }

  if (!res.ok) {
    const message =
      (data as { error?: string })?.error || res.statusText || "request failed";
    throw new ApiError(res.status, message);
  }

  return data as T;
}
