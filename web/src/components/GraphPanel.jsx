import React, { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

export default function GraphPanel({ data, center }) {
  const wrapRef = useRef(null);
  const [width, setWidth] = useState(600);

  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width);
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  // react-force-graph mutates the graph object, so give it a stable, cloned copy.
  const graphData = useMemo(() => {
    const nodes = (data?.nodes || []).map((n) => ({ ...n }));
    const links = (data?.links || []).map((l) => ({ ...l }));
    return { nodes, links };
  }, [data]);

  const shared = data?.shared_devices || [];
  const colocated = data?.co_located || [];

  return (
    <div className="panel graph-panel">
      <h3>Contact network ({graphData.nodes.length} nodes, {graphData.links.length} links)</h3>
      <div className="graph-wrap" ref={wrapRef}>
        <ForceGraph2D
          graphData={graphData}
          width={width}
          height={360}
          nodeId="id"
          nodeLabel={(n) => `${n.name || ""}\n${n.id}`}
          nodeColor={(n) => (n.id === center ? "#e4572e" : "#3a86ff")}
          nodeRelSize={5}
          linkColor={() => "rgba(120,120,120,0.4)"}
          linkWidth={(l) => Math.min(1 + Math.log10((l.calls || 1) + 1), 4)}
          cooldownTicks={80}
        />
      </div>

      <div className="detect-grid">
        <div className="detect-col">
          <h4>Shared devices ({shared.length})</h4>
          {shared.length === 0 ? (
            <p className="muted">None detected.</p>
          ) : (
            <ul>
              {shared.map((d, i) => (
                <li key={i}>
                  <code>{d.imei}</code> ({d.model}) — also {d.number} {d.name}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="detect-col">
          <h4>Co-located subscribers ({colocated.length})</h4>
          {colocated.length === 0 ? (
            <p className="muted">None detected.</p>
          ) : (
            <ul>
              {colocated.slice(0, 20).map((c, i) => (
                <li key={i}>
                  {c.number} {c.name} — {c.shared_towers} tower
                  {c.shared_towers === 1 ? "" : "s"} ({c.locations.join(", ")})
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
