import React, { useState } from "react";
import { useLink } from "../api.js";

export default function LinkPanel({ a }) {
  const [bInput, setBInput] = useState("");
  const [b, setB] = useState("");
  const { data, isLoading, isError, error } = useLink(a, b);

  function submit(e) {
    e.preventDefault();
    const n = bInput.trim();
    if (n) setB(n);
  }

  return (
    <div className="panel">
      <h3>Link analysis</h3>
      <form className="searchbar" onSubmit={submit}>
        <input
          type="text"
          inputMode="numeric"
          placeholder={`How is ${a} connected to… (enter a second number)`}
          value={bInput}
          onChange={(e) => setBInput(e.target.value)}
        />
        <button type="submit">Analyze</button>
      </form>

      {b && isLoading && <p className="muted">Analyzing…</p>}
      {b && isError && <p className="error">{String(error.message)}</p>}

      {b && data && (
        <div className="link-result">
          <div className="stat-row">
            <div className="stat">
              <div className="stat-num">{data.direct_calls || 0}</div>
              <div className="stat-label">Direct calls</div>
            </div>
            <div className="stat">
              <div className="stat-num">{Math.round((data.direct_duration || 0) / 60)}</div>
              <div className="stat-label">Direct minutes</div>
            </div>
            <div className="stat">
              <div className="stat-num">{data.hops > 0 ? data.hops : "∞"}</div>
              <div className="stat-label">Shortest path (hops)</div>
            </div>
          </div>

          {data.path?.length > 0 && (
            <p className="path">
              {data.path.map((h, i) => (
                <span key={i}>
                  <span className="chip" title={h.name}>{h.number}</span>
                  {i < data.path.length - 1 && <span className="arrow"> → </span>}
                </span>
              ))}
            </p>
          )}

          <div className="detect-grid">
            <div className="detect-col">
              <h4>Common contacts ({data.common_contacts?.length || 0})</h4>
              {data.common_contacts?.length ? (
                <ul>
                  {data.common_contacts.map((c, i) => (
                    <li key={i}>{c.id} {c.name}</li>
                  ))}
                </ul>
              ) : <p className="muted">None.</p>}
            </div>
            <div className="detect-col">
              <h4>Shared towers ({data.shared_towers?.length || 0})</h4>
              {data.shared_towers?.length ? (
                <ul>
                  {data.shared_towers.map((t, i) => (
                    <li key={i}><code>{t.number}</code> {t.locations?.join(", ")}</li>
                  ))}
                </ul>
              ) : <p className="muted">None.</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
