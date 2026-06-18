import React, { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip } from "react-leaflet";
import { useTrajectory } from "../api.js";

const ETHIOPIA_CENTER = [9.145, 40.4897];

export default function TrajectoryPanel({ number }) {
  const { data, isLoading } = useTrajectory(number);
  const points = data?.points || [];
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    setIdx(0);
    setPlaying(false);
  }, [number]);

  useEffect(() => {
    if (!playing || points.length === 0) return;
    timer.current = setInterval(() => {
      setIdx((i) => {
        if (i >= points.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 250);
    return () => clearInterval(timer.current);
  }, [playing, points.length]);

  const latlngs = useMemo(() => points.map((p) => [p.latitude, p.longitude]), [points]);
  const trail = latlngs.slice(0, idx + 1);
  const cur = points[idx];
  const center = cur ? [cur.latitude, cur.longitude] : ETHIOPIA_CENTER;

  if (isLoading) return <div className="panel"><h3>Movement trajectory</h3><p className="muted">Loading…</p></div>;
  if (points.length === 0) return null;

  return (
    <div className="panel">
      <h3>Movement trajectory ({points.length} points)</h3>
      <div className="map-wrap">
        <MapContainer center={center} zoom={6} scrollWheelZoom>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; OpenStreetMap contributors' />
          <Polyline positions={trail} pathOptions={{ color: "#3a86ff", weight: 2, opacity: 0.7 }} />
          {cur && (
            <CircleMarker center={[cur.latitude, cur.longitude]} radius={9}
              pathOptions={{ color: "#e4572e", fillColor: "#e4572e", fillOpacity: 0.9 }}>
              <Tooltip permanent>{cur.location_name} · {cur.time?.slice(0, 16)}</Tooltip>
            </CircleMarker>
          )}
        </MapContainer>
      </div>
      <div className="playbar">
        <button onClick={() => { if (idx >= points.length - 1) setIdx(0); setPlaying((p) => !p); }}>
          {playing ? "⏸ Pause" : "▶ Play"}
        </button>
        <input type="range" min={0} max={points.length - 1} value={idx}
          onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)); }} />
        <span className="muted small">{cur?.time?.slice(0, 16)} · {cur?.location_name}</span>
      </div>
    </div>
  );
}
