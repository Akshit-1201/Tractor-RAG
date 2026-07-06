// Base fetch wrapper. Relative /api paths go through the Vite dev proxy (spec §11.4).
const BASE = "/api";

export function authHeader(): Record<string, string> {
  const token = localStorage.getItem("admin_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  // Never set Content-Type for FormData — the browser adds the multipart boundary.
  const isForm = init.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isForm ? {} : { "Content-Type": "application/json" }),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  const response = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}
