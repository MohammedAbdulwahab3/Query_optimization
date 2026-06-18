// ===========================================================================
// Memgraph reference queries — graph model + relationship detection
// ===========================================================================
// Graph model written by the ingest job:
//   Nodes:
//     (:Subscriber {number, name, imsi, operator, reg_date})
//     (:Device     {imei, model})
//     (:Cell       {cell_id, lat, lon, location_name})
//   Edges:
//     (:Subscriber)-[:CALLED {start, duration, type, calls, total_duration}]->(:Subscriber)
//     (:Subscriber)-[:USED]->(:Device)
//     (:Subscriber)-[:CONNECTED_AT {time, connections}]->(:Cell)
//
// Note: CALLED is aggregated per (caller, callee) pair (with a `calls` count)
// rather than one edge per call — the per-call event log lives in ClickHouse
// (the timeline). The graph store models *relationships* for network analysis.
// ===========================================================================


// --- Contact network, depth 1 (direct contacts of a number) -----------------
MATCH (s:Subscriber {number: $number})-[e:CALLED]-(contact:Subscriber)
RETURN contact.number AS number, contact.name AS name,
       e.calls AS calls, e.total_duration AS total_duration
ORDER BY calls DESC;


// --- Contact network, depth 1-2 (contacts and their contacts) ---------------
MATCH path = (s:Subscriber {number: $number})-[:CALLED*1..2]-(other:Subscriber)
WHERE other.number <> $number
RETURN DISTINCT other.number AS number, other.name AS name,
       length(path) AS hops
ORDER BY hops, number;


// --- SHARED-DEVICE DETECTION ------------------------------------------------
// Two or more subscribers that used the same physical handset (IMEI) — a
// classic signal of swapped SIMs / shared phones.
MATCH (a:Subscriber)-[:USED]->(d:Device)<-[:USED]-(b:Subscriber)
WHERE a.number < b.number
RETURN d.imei AS imei, d.model AS model,
       collect(a.number) + collect(b.number) AS subscribers;

// Shared device for one specific number of interest:
MATCH (s:Subscriber {number: $number})-[:USED]->(d:Device)<-[:USED]-(other:Subscriber)
WHERE other.number <> s.number
RETURN d.imei AS imei, d.model AS model,
       other.number AS also_used_by, other.name AS name;


// --- CO-LOCATED TOWER DETECTION ---------------------------------------------
// Other subscribers seen connecting at the same cell towers as the target —
// a proxy for physical co-location.
MATCH (s:Subscriber {number: $number})-[:CONNECTED_AT]->(c:Cell)<-[:CONNECTED_AT]-(other:Subscriber)
WHERE other.number <> s.number
RETURN other.number AS number, other.name AS name,
       collect(DISTINCT c.location_name) AS shared_locations,
       count(DISTINCT c) AS shared_towers
ORDER BY shared_towers DESC
LIMIT 50;
