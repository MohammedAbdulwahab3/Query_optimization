import React, { useState } from "react";
import SearchBar from "./components/SearchBar.jsx";
import ProfilePanel from "./components/ProfilePanel.jsx";
import MapPanel from "./components/MapPanel.jsx";
import GraphPanel from "./components/GraphPanel.jsx";
import TimelineTable from "./components/TimelineTable.jsx";
import CoLocationPanel from "./components/CoLocationPanel.jsx";
import LinkPanel from "./components/LinkPanel.jsx";
import FlagsPanel from "./components/FlagsPanel.jsx";
import AlertsView from "./components/AlertsView.jsx";
import { useSearch, useGraph } from "./api.js";

export default function App() {
  const [number, setNumber] = useState("");
  const [tab, setTab] = useState("search"); // search | alerts

  const search = useSearch(number);
  const graph = useGraph(number);

  function pick(n) {
    setNumber(n);
    setTab("search");
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>📡 Telecom CDR Analytics</h1>
        <span className="tag">INSA · lawful-interception demo · synthetic data</span>
        <nav className="tabs">
          <button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>Search</button>
          <button className={tab === "alerts" ? "active" : ""} onClick={() => setTab("alerts")}>Alerts</button>
        </nav>
      </header>

      {tab === "alerts" && <AlertsView onPick={pick} />}

      {tab === "search" && (
        <>
          <SearchBar onSearch={setNumber} initial={number} />

          {!number && (
            <div className="empty">
              <p>Search a subscriber number to view their profile, locations,
                contact network, risk flags, and call timeline.</p>
              <p className="muted">Or open the <strong>Alerts</strong> tab to see
                dataset-wide suspicious patterns and click a number to investigate.</p>
            </div>
          )}

          {number && search.isLoading && <p className="muted">Loading profile…</p>}
          {number && search.isError && (
            <p className="error">Could not load {number}: {String(search.error.message)}</p>
          )}

          {number && search.data && (
            <>
              <div className="top-grid">
                <ProfilePanel profile={search.data.profile} />
                <MapPanel points={search.data.map_points} />
              </div>

              <FlagsPanel number={number} />

              {graph.isLoading && <p className="muted">Loading contact network…</p>}
              {graph.data && <GraphPanel data={graph.data} center={number} />}

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
