import React from "react";
import { useFlags } from "../api.js";

export default function FlagsPanel({ number }) {
  const { data, isLoading } = useFlags(number);
  if (isLoading || !data) return null;
  const flags = data.flags || [];

  return (
    <div className="panel">
      <h3>Risk flags ({flags.length})</h3>
      {flags.length === 0 ? (
        <p className="muted">No suspicious patterns detected.</p>
      ) : (
        <div className="flag-list">
          {flags.map((f, i) => (
            <div key={i} className={`flag sev-${f.severity}`}>
              <span className="flag-label">{f.label}</span>
              <span className="flag-detail">{f.detail}</span>
            </div>
          ))}
        </div>
      )}
      <div className="metric-row">
        <span>{data.total_calls} calls</span>
        <span>{data.contacts} contacts</span>
        <span>{data.active_days} active days</span>
        <span>{Math.round((data.out_ratio || 0) * 100)}% outgoing</span>
        <span>{Math.round((data.night_ratio || 0) * 100)}% night</span>
      </div>
    </div>
  );
}
