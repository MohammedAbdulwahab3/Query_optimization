package main

import (
	"context"

	"github.com/neo4j/neo4j-go-driver/v5/neo4j"
)

// MGStore wraps a Memgraph (Bolt) driver. All Cypher uses $param bindings.
type MGStore struct {
	driver neo4j.DriverWithContext
}

func newMGStore(cfg Config) (*MGStore, error) {
	var auth neo4j.AuthToken
	if cfg.MemgraphUser != "" {
		auth = neo4j.BasicAuth(cfg.MemgraphUser, cfg.MemgraphPassword, "")
	} else {
		auth = neo4j.NoAuth()
	}
	d, err := neo4j.NewDriverWithContext(cfg.MemgraphURI, auth)
	if err != nil {
		return nil, err
	}
	return &MGStore{driver: d}, nil
}

func (s *MGStore) ping(ctx context.Context) error {
	return s.driver.VerifyConnectivity(ctx)
}

func (s *MGStore) close(ctx context.Context) { _ = s.driver.Close(ctx) }

// --- result types ---

type GraphNode struct {
	ID   string `json:"id"`   // phone number
	Name string `json:"name"`
}

type GraphLink struct {
	Source string `json:"source"`
	Target string `json:"target"`
	Calls  int64  `json:"calls"`
}

type SharedDevice struct {
	IMEI  string `json:"imei"`
	Model string `json:"model"`
	Number string `json:"number"`
	Name   string `json:"name"`
}

type CoLocated struct {
	Number       string   `json:"number"`
	Name         string   `json:"name"`
	Locations    []string `json:"locations"`
	SharedTowers int64    `json:"shared_towers"`
}

type GraphResult struct {
	Center        string         `json:"center"`
	Nodes         []GraphNode    `json:"nodes"`
	Links         []GraphLink    `json:"links"`
	SharedDevices []SharedDevice `json:"shared_devices"`
	CoLocated     []CoLocated    `json:"co_located"`
}

// Graph returns the depth-1..2 contact network (as force-graph nodes/links),
// plus shared-device and co-located-tower detection for the given number.
func (s *MGStore) Graph(ctx context.Context, number string, depth int) (*GraphResult, error) {
	sess := s.driver.NewSession(ctx, neo4j.SessionConfig{AccessMode: neo4j.AccessModeRead})
	defer sess.Close(ctx)

	res := &GraphResult{
		Center:        number,
		Nodes:         []GraphNode{},
		Links:         []GraphLink{},
		SharedDevices: []SharedDevice{},
		CoLocated:     []CoLocated{},
	}
	nodeSet := map[string]bool{}
	addNode := func(id, name string) {
		if id == "" || nodeSet[id] {
			return
		}
		nodeSet[id] = true
		res.Nodes = append(res.Nodes, GraphNode{ID: id, Name: name})
	}

	// Contact network edges within `depth` hops. Memgraph supports variable-
	// length patterns; depth is clamped to 1..2 by the caller.
	cypherEdges := `
		MATCH path = (s:Subscriber {number: $number})-[:CALLED*1..2]-(o:Subscriber)
		UNWIND relationships(path) AS rel
		WITH DISTINCT startNode(rel) AS a, endNode(rel) AS b, rel
		RETURN a.number AS source, a.name AS source_name,
		       b.number AS target, b.name AS target_name,
		       coalesce(rel.calls, 1) AS calls
		LIMIT 500`
	if depth == 1 {
		cypherEdges = `
			MATCH (s:Subscriber {number: $number})-[rel:CALLED]-(o:Subscriber)
			RETURN s.number AS source, s.name AS source_name,
			       o.number AS target, o.name AS target_name,
			       coalesce(rel.calls, 1) AS calls
			LIMIT 500`
	}

	r, err := sess.Run(ctx, cypherEdges, map[string]any{"number": number})
	if err != nil {
		return nil, err
	}
	for r.Next(ctx) {
		rec := r.Record()
		source, _ := rec.Get("source")
		target, _ := rec.Get("target")
		sName, _ := rec.Get("source_name")
		tName, _ := rec.Get("target_name")
		calls, _ := rec.Get("calls")
		src, _ := source.(string)
		tgt, _ := target.(string)
		addNode(src, asString(sName))
		addNode(tgt, asString(tName))
		res.Links = append(res.Links, GraphLink{Source: src, Target: tgt, Calls: asInt64(calls)})
	}
	if err := r.Err(); err != nil {
		return nil, err
	}
	addNode(number, "") // ensure the center is present even with no edges

	// Shared-device detection.
	r, err = sess.Run(ctx, `
		MATCH (s:Subscriber {number: $number})-[:USED]->(d:Device)<-[:USED]-(other:Subscriber)
		WHERE other.number <> s.number
		RETURN d.imei AS imei, d.model AS model,
		       other.number AS number, other.name AS name`,
		map[string]any{"number": number})
	if err != nil {
		return nil, err
	}
	for r.Next(ctx) {
		rec := r.Record()
		imei, _ := rec.Get("imei")
		model, _ := rec.Get("model")
		num, _ := rec.Get("number")
		name, _ := rec.Get("name")
		res.SharedDevices = append(res.SharedDevices, SharedDevice{
			IMEI: asString(imei), Model: asString(model),
			Number: asString(num), Name: asString(name),
		})
	}
	if err := r.Err(); err != nil {
		return nil, err
	}

	// Co-located-tower detection.
	r, err = sess.Run(ctx, `
		MATCH (s:Subscriber {number: $number})-[:CONNECTED_AT]->(c:Cell)<-[:CONNECTED_AT]-(other:Subscriber)
		WHERE other.number <> s.number
		RETURN other.number AS number, other.name AS name,
		       collect(DISTINCT c.location_name) AS locations,
		       count(DISTINCT c) AS shared_towers
		ORDER BY shared_towers DESC
		LIMIT 50`,
		map[string]any{"number": number})
	if err != nil {
		return nil, err
	}
	for r.Next(ctx) {
		rec := r.Record()
		num, _ := rec.Get("number")
		name, _ := rec.Get("name")
		locs, _ := rec.Get("locations")
		towers, _ := rec.Get("shared_towers")
		res.CoLocated = append(res.CoLocated, CoLocated{
			Number: asString(num), Name: asString(name),
			Locations: asStringSlice(locs), SharedTowers: asInt64(towers),
		})
	}
	return res, r.Err()
}

// --- small type coercion helpers for Bolt's any-typed values ---

func asString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func asInt64(v any) int64 {
	switch n := v.(type) {
	case int64:
		return n
	case int:
		return int64(n)
	case float64:
		return int64(n)
	}
	return 0
}

func asStringSlice(v any) []string {
	out := []string{}
	if arr, ok := v.([]any); ok {
		for _, e := range arr {
			if s, ok := e.(string); ok {
				out = append(out, s)
			}
		}
	}
	return out
}
