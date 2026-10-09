"use client";

let csrfToken = "";

export function setCsrf(token: string) {
  csrfToken = token;
}

export async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  try {
    const res = await fetch("/api/auth/me", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (res.ok) {
      const d = (await res.json()) as { csrf?: string };
      if (d?.csrf) csrfToken = d.csrf;
    }
  } catch {
    // ignore: the caller will surface a real error
  }
  return csrfToken;
}

async function parse<T>(res: Response, path: string): Promise<T> {
  if (res.status === 401 && !path.startsWith("/auth/")) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("เซสชันหมดอายุ");
  }
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
    throw new Error(
      (data as { error?: string })?.error || res.statusText || "request failed",
    );
  }
  return data as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    cache: "no-store",
  });
  return parse<T>(res, path);
}

export async function apiSend<T = unknown>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const csrf = await ensureCsrf();
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
    },
    body: JSON.stringify(body ?? {}),
  });
  return parse<T>(res, path);
}
