import React from "react";

function Field({ label, value }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{value ?? "—"}</span>
    </div>
  );
}

export default function ProfilePanel({ profile }) {
  if (!profile) return null;
  const minutes = Math.round((profile.total_minutes || 0) * 10) / 10;
  return (
    <div className="panel profile">
      <div className="profile-header">
        <h2>{profile.subscriber_name || "Unknown"}</h2>
        <span className={`badge ${profile.operator === "Safaricom" ? "saf" : "ethio"}`}>
          {profile.operator}
        </span>
      </div>
      <div className="profile-grid">
        <Field label="Number" value={profile.number} />
        <Field label="Device" value={profile.device_model} />
        <Field label="IMEI" value={profile.imei} />
        <Field label="IMSI" value={profile.imsi} />
        <Field label="Registered" value={profile.registration_date} />
      </div>
      <div className="stat-row">
        <div className="stat">
          <div className="stat-num">{(profile.call_count || 0).toLocaleString()}</div>
          <div className="stat-label">Calls</div>
        </div>
        <div className="stat">
          <div className="stat-num">{minutes.toLocaleString()}</div>
          <div className="stat-label">Minutes</div>
        </div>
      </div>
    </div>
  );
}
