import { useQuery } from "@tanstack/react-query";

// All requests go through /api, which Vite (dev) and nginx (prod) proxy to the
// Go service. Override with VITE_API_BASE if needed.
const BASE = import.meta.env.VITE_API_BASE || "/api";

const TOKEN_KEY = "cdr_token";
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(t) {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = await res.json();
  setToken(data.token);
  return data;
}

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.error) msg = body.error;
    } catch {
      /* ignore */
    }
    if (res.status === 401) {
      clearToken();
      window.dispatchEvent(new Event("auth-expired"));
    }
    throw new HttpError(res.status, msg);
  }
  return res.json();
}

export function useSearch(number) {
  return useQuery({
    queryKey: ["search", number],
    queryFn: () => getJSON(`/search/${number}`),
    enabled: !!number,
  });
}

export function useGraph(number, depth = 2) {
  return useQuery({
    queryKey: ["graph", number, depth],
    queryFn: () => getJSON(`/graph/${number}?depth=${depth}`),
    enabled: !!number,
  });
}

export function useAudit(enabled) {
  return useQuery({
    queryKey: ["audit"],
    queryFn: () => getJSON(`/audit`),
    enabled: !!enabled,
    refetchInterval: 5000,
  });
}

export function usePatterns(number) {
  return useQuery({
    queryKey: ["patterns", number],
    queryFn: () => getJSON(`/patterns/${number}`),
    enabled: !!number,
  });
}

export function useTrajectory(number) {
  return useQuery({
    queryKey: ["trajectory", number],
    queryFn: () => getJSON(`/trajectory/${number}?limit=500`),
    enabled: !!number,
  });
}

export function useSamples(enabled) {
  return useQuery({
    queryKey: ["samples"],
    queryFn: () => getJSON(`/samples`),
    enabled: !!enabled,
  });
}

export function useFlags(number) {
  return useQuery({
    queryKey: ["flags", number],
    queryFn: () => getJSON(`/flags/${number}`),
    enabled: !!number,
  });
}

export function useAlerts(enabled) {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => getJSON(`/alerts`),
    enabled: !!enabled,
  });
}

export function useColocation(number, windowMin = 10) {
  return useQuery({
    queryKey: ["colocation", number, windowMin],
    queryFn: () => getJSON(`/colocation/${number}?window=${windowMin}`),
    enabled: !!number,
  });
}

export function useLink(a, b) {
  return useQuery({
    queryKey: ["link", a, b],
    queryFn: () => getJSON(`/link/${a}/${b}`),
    enabled: !!a && !!b,
  });
}

export function useTimeline(number, { page, pageSize, from, to }) {
  const params = new URLSearchParams({ page, page_size: pageSize });
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  return useQuery({
    queryKey: ["timeline", number, page, pageSize, from, to],
    queryFn: () => getJSON(`/timeline/${number}?${params.toString()}`),
    enabled: !!number,
    placeholderData: (prev) => prev,
  });
}
