import React, { useState } from "react";
import SearchBar from "./components/SearchBar.jsx";
import ProfilePanel from "./components/ProfilePanel.jsx";
import MapPanel from "./components/MapPanel.jsx";
import GraphPanel from "./components/GraphPanel.jsx";
import TimelineTable from "./components/TimelineTable.jsx";
import CoLocationPanel from "./components/CoLocationPanel.jsx";
import LinkPanel from "./components/LinkPanel.jsx";
import { useSearch, useGraph } from "./api.js";

export default function App() {
  const [number, setNumber] = useState("");

  const search = useSearch(number);
  const graph = useGraph(number);

  return (
    <div className="app">
      <header className="app-header">
        <h1>📡 Telecom CDR Analytics</h1>
        <span className="tag">INSA · lawful-interception demo · synthetic data</span>
      </header>

      <SearchBar onSearch={setNumber} initial={number} />

      {!number && (
        <div className="empty">
          <p>Search a subscriber number to view their profile, locations,
            contact network, and call timeline.</p>
          <p className="muted">Try a number from the seeded dataset (e.g. one
            shown in another subscriber's contact graph).</p>
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

          {graph.isLoading && <p className="muted">Loading contact network…</p>}
          {graph.data && <GraphPanel data={graph.data} center={number} />}

          <LinkPanel a={number} />
          <CoLocationPanel number={number} />
          <TimelineTable number={number} />
        </>
      )}
    </div>
  );
}
