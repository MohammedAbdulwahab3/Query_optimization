import React from "react";
import { useSamples } from "../api.js";

export default function SampleTargets({ onPick }) {
  const { data, isLoading } = useSamples(true);
  const samples = data?.samples || [];
  if (isLoading || samples.length === 0) return null;

  return (
    <div className="samples">
      <p className="muted small">Warranted targets you can open right now:</p>
      <div className="sample-chips">
        {samples.map((s) => (
          <button key={s.number} className="sample-chip" onClick={() => onPick(s.number)}
            title={s.reason}>
            <span className="sample-num">{s.number}</span>
            <span className="sample-name">{s.name || "—"}</span>
            <span className="sample-reason">{s.reason}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
