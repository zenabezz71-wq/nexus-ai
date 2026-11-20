export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Me = {
  name: string;
  organization_name: string;
  role: string;
  permissions?: string[];
  is_platform_admin?: boolean;
};

export async function apiFetch(path: string, init: RequestInit = {}) {
  const token = localStorage.getItem("nexus_token") || "";
  const h = new Headers(init.headers || {});
  if (token) h.set("Authorization", `Bearer ${token}`);
  if (init.body) h.set("Content-Type", "application/json");
  const r = await fetch(API + path, { ...init, headers: h });
  if (r.status === 401) {
    localStorage.removeItem("nexus_token");
    window.location.replace("/");
    throw new Error("Session expired. Please sign in again.");
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const det = (d as { detail?: unknown })?.detail;
    throw new Error(
      typeof det === "string"
        ? det
        : Array.isArray(det)
        ? det.map((x: { msg?: string }) => x.msg || "").filter(Boolean).join(", ")
        : `Request failed (${r.status})`
    );
  }
  return d;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString();
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
}
