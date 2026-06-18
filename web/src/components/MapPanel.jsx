import React from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";

// Center on Ethiopia by default.
const ETHIOPIA_CENTER = [9.145, 40.4897];

export default function MapPanel({ points }) {
  const pts = points || [];
  const center = pts.length ? [pts[0].latitude, pts[0].longitude] : ETHIOPIA_CENTER;
  const maxHits = pts.reduce((m, p) => Math.max(m, p.hits || 1), 1);

  return (
    <div className="panel map-panel">
      <h3>Call locations ({pts.length} towers)</h3>
      <div className="map-wrap">
        <MapContainer center={center} zoom={pts.length ? 7 : 6} scrollWheelZoom>
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {pts.map((p, i) => (
            <CircleMarker
              key={i}
              center={[p.latitude, p.longitude]}
              radius={6 + 14 * Math.sqrt((p.hits || 1) / maxHits)}
              pathOptions={{ color: "#e4572e", fillColor: "#e4572e", fillOpacity: 0.5 }}
            >
              <Tooltip>
                {p.location_name} — {p.hits} connection{p.hits === 1 ? "" : "s"}
              </Tooltip>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
