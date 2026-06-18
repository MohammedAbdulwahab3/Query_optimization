import React, { useEffect, useState } from "react";
import SearchBar from "./components/SearchBar.jsx";
import ProfilePanel from "./components/ProfilePanel.jsx";
import MapPanel from "./components/MapPanel.jsx";
import GraphPanel from "./components/GraphPanel.jsx";
import TimelineTable from "./components/TimelineTable.jsx";
import CoLocationPanel from "./components/CoLocationPanel.jsx";
import LinkPanel from "./components/LinkPanel.jsx";
import FlagsPanel from "./components/FlagsPanel.jsx";
import PatternsPanel from "./components/PatternsPanel.jsx";
import TrajectoryPanel from "./components/TrajectoryPanel.jsx";
import AlertsView from "./components/AlertsView.jsx";
import AuditView from "./components/AuditView.jsx";
import LoginScreen from "./components/LoginScreen.jsx";
import { useSearch, useGraph, getToken, clearToken } from "./api.js";

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [analyst, setAnalyst] = useState("");
  const [number, setNumber] = useState("");
  const [tab, setTab] = useState("search"); // search | alerts | audit

  const search = useSearch(authed ? number : "");
  const graph = useGraph(authed ? number : "");

  useEffect(() => {
    const onExpire = () => setAuthed(false);
    window.addEventListener("auth-expired", onExpire);
    return () => window.removeEventListener("auth-expired", onExpire);
  }, []);

  if (!authed) {
    return <LoginScreen onLogin={(a) => { setAnalyst(a); setAuthed(true); }} />;
  }

  function pick(n) {
    setNumber(n);
    setTab("search");
  }
  function logout() {
    clearToken();
    setAuthed(false);
    setNumber("");
  }

  const denied = search.isError && search.error?.status === 403;

  return (
    <div className="app">
      <header className="app-header">
        <h1>📡 Telecom CDR Analytics</h1>
        <span className="tag">INSA · lawful-interception demo · synthetic data</span>
        <nav className="tabs">
          <button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>Search</button>
          <button className={tab === "alerts" ? "active" : ""} onClick={() => setTab("alerts")}>Alerts</button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>Audit</button>
          <button className="logout" onClick={logout}>⎋ {analyst || "Sign out"}</button>
        </nav>
      </header>

      {tab === "alerts" && <AlertsView onPick={pick} />}
      {tab === "audit" && <AuditView />}

      {tab === "search" && (
        <>
          <SearchBar onSearch={setNumber} initial={number} />

          {!number && (
            <div className="empty">
              <p>Search a subscriber number to view their profile, locations,
                contact network, risk flags, movements, and call timeline.</p>
              <p className="muted">Access is gated by an active <strong>warrant</strong>; every
                lookup is recorded in the <strong>Audit</strong> log. Open <strong>Alerts</strong>
                for dataset-wide suspicious patterns.</p>
            </div>
          )}

          {number && search.isLoading && <p className="muted">Loading profile…</p>}
          {denied && (
            <div className="panel warrant-deny">
              <h3>⛔ Access denied</h3>
              <p>No active warrant covers <code>{number}</code>. This access attempt
                has been recorded in the audit log.</p>
            </div>
          )}
          {number && search.isError && !denied && (
            <p className="error">Could not load {number}: {String(search.error.message)}</p>
          )}

          {number && search.data && (
            <>
              <div className="top-grid">
                <ProfilePanel profile={search.data.profile} />
                <MapPanel points={search.data.map_points} />
              </div>

              <FlagsPanel number={number} />
              <PatternsPanel number={number} />

              {graph.isLoading && <p className="muted">Loading contact network…</p>}
              {graph.data && <GraphPanel data={graph.data} center={number} />}

              <TrajectoryPanel number={number} />
              <LinkPanel a={number} />
              <CoLocationPanel number={number} />
              <TimelineTable number={number} />
            </>
          )}
        </>
      )}
    </div>
  );
}
