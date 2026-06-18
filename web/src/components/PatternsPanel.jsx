import React from "react";
import { usePatterns } from "../api.js";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function PatternsPanel({ number }) {
  const { data, isLoading } = usePatterns(number);
  if (isLoading || !data) return null;

  // grid[dowIndex 0..6][hour 0..23]
  const grid = Array.from({ length: 7 }, () => Array(24).fill(0));
  let max = 0;
  for (const c of data.heatmap || []) {
    const d = (c.dow - 1) % 7; // dow 1=Mon
    grid[d][c.hour] = c.calls;
    if (c.calls > max) max = c.calls;
  }
  const color = (v) => {
    if (!v) return "var(--panel-2)";
    const t = v / max;
    return `rgba(58,134,255,${0.15 + 0.85 * t})`;
  };

  return (
    <div className="panel">
      <h3>Pattern of life</h3>
      <div className="heatmap">
        <div className="hm-row hm-head">
          <span className="hm-label"></span>
          {Array.from({ length: 24 }, (_, h) => (
            <span key={h} className="hm-hour">{h % 6 === 0 ? h : ""}</span>
          ))}
        </div>
        {grid.map((row, d) => (
          <div className="hm-row" key={d}>
            <span className="hm-label">{DOW[d]}</span>
            {row.map((v, h) => (
              <span key={h} className="hm-cell" style={{ background: color(v) }}
                title={`${DOW[d]} ${h}:00 — ${v} calls`} />
            ))}
          </div>
        ))}
      </div>
      <div className="towers">
        <div className="tower-card">
          <span className="tower-kind">🏠 Home (night)</span>
          {data.home ? <span>{data.home.location_name} · <code>{data.home.cell_id}</code> ({data.home.count})</span>
            : <span className="muted">—</span>}
        </div>
        <div className="tower-card">
          <span className="tower-kind">🏢 Work (weekday daytime)</span>
          {data.work ? <span>{data.work.location_name} · <code>{data.work.cell_id}</code> ({data.work.count})</span>
            : <span className="muted">—</span>}
        </div>
      </div>
    </div>
  );
}
