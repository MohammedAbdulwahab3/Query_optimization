import React from "react";
import { useAudit } from "../api.js";

export default function AuditView() {
  const { data, isLoading, isError, error } = useAudit(true);
  const entries = data?.entries || [];

  return (
    <div className="panel">
      <h3>Audit log ({entries.length}) — live</h3>
      <p className="muted small">Every analyst access to a number is recorded here (allowed or denied).</p>
      {isLoading && <p className="muted">Loading…</p>}
      {isError && <p className="error">{String(error.message)}</p>}
      {entries.length > 0 && (
        <table className="mini-table">
          <thead>
            <tr><th>Time</th><th>Analyst</th><th>Action</th><th>Target</th><th>Warrant</th><th>Result</th><th>IP</th></tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={i}>
                <td>{e.ts}</td>
                <td>{e.analyst}</td>
                <td>{e.action}</td>
                <td className="c-num">{e.target}</td>
                <td>{e.warrant_id || "—"}</td>
                <td className={e.result === "denied" ? "res-failed" : "res-answered"}>{e.result}</td>
                <td>{e.client_ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
