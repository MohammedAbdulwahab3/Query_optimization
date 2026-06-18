import React, { useState } from "react";
import { useColocation } from "../api.js";

const WINDOWS = [5, 10, 30, 60];

function fmt(ts) {
  if (!ts) return "—";
  return new Date(ts.replace(" ", "T")).toLocaleString();
}

export default function CoLocationPanel({ number }) {
  const [win, setWin] = useState(10);
  const { data, isLoading, isError, error } = useColocation(number, win);
  const rows = data?.co_located || [];

  return (
    <div className="panel">
      <div className="timeline-head">
        <h3>Co-location in time + space ({rows.length})</h3>
        <div className="filters">
          <label>
            Window
            <select value={win} onChange={(e) => setWin(Number(e.target.value))}>
              {WINDOWS.map((w) => (
                <option key={w} value={w}>±{w} min</option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <p className="muted small">
        Other subscribers connected at the <strong>same tower within ±{win} min</strong> of
        this number — a stronger physical-proximity signal than sharing a tower at any time.
      </p>

      {isLoading && <p className="muted">Loading…</p>}
      {isError && <p className="error">{String(error.message)}</p>}
      {!isLoading && rows.length === 0 && <p className="muted">No co-located events in this window.</p>}

      {rows.length > 0 && (
        <table className="mini-table">
          <thead>
            <tr><th>Number</th><th>Events</th><th>First seen</th><th>Last seen</th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="c-num">{r.number}</td>
                <td>{r.events}</td>
                <td>{fmt(r.first_seen)}</td>
                <td>{fmt(r.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
