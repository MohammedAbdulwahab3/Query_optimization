import React from "react";
import { useAlerts } from "../api.js";

export default function AlertsView({ onPick }) {
  const { data, isLoading, isError, error } = useAlerts(true);

  if (isLoading) return <p className="muted">Scanning dataset for suspicious patterns…</p>;
  if (isError) return <p className="error">{String(error.message)}</p>;
  if (!data) return null;

  const Num = ({ n }) => (
    <button className="linkbtn" onClick={() => onPick(n)}>{n}</button>
  );

  return (
    <div className="alerts">
      <div className="panel">
        <h3>🔴 SIM-swap — shared handsets ({data.sim_swap?.length || 0})</h3>
        <p className="muted small">One IMEI used by multiple numbers — possible SIM swapping.</p>
        <table className="mini-table">
          <thead><tr><th>IMEI</th><th>#</th><th>Numbers</th></tr></thead>
          <tbody>
            {(data.sim_swap || []).map((g, i) => (
              <tr key={i}>
                <td><code>{g.imei}</code></td>
                <td>{g.count}</td>
                <td>{g.numbers.map((n, j) => (
                  <React.Fragment key={j}>{j > 0 && ", "}<Num n={n} /></React.Fragment>
                ))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="two-col">
        <div className="panel">
          <h3>📵 Possible burners ({data.burners?.length || 0})</h3>
          <p className="muted small">Few contacts, short-lived, low volume.</p>
          <table className="mini-table">
            <thead><tr><th>Number</th><th>Calls</th><th>Contacts</th><th>Days</th></tr></thead>
            <tbody>
              {(data.burners || []).map((b, i) => (
                <tr key={i}>
                  <td><Num n={b.number} /></td>
                  <td>{b.calls}</td><td>{b.contacts}</td><td>{b.active_days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h3>🌙 Night-active numbers ({data.night_owls?.length || 0})</h3>
          <p className="muted small">≥40% of calls between 00:00–05:00.</p>
          <table className="mini-table">
            <thead><tr><th>Number</th><th>Calls</th><th>Night %</th></tr></thead>
            <tbody>
              {(data.night_owls || []).map((o, i) => (
                <tr key={i}>
                  <td><Num n={o.number} /></td>
                  <td>{o.calls}</td>
                  <td>{Math.round(o.night_ratio * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
