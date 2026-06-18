import { useQuery } from "@tanstack/react-query";

// All requests go through /api, which Vite (dev) and nginx (prod) proxy to the
// Go service. Override with VITE_API_BASE if needed.
const BASE = import.meta.env.VITE_API_BASE || "/api";

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.error) msg = body.error;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
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
