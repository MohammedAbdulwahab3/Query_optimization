import React, { useState } from "react";
import { login } from "../api.js";

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("agent.alem");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { analyst } = await login(username, password);
      onLogin(analyst);
    } catch (err) {
      setError(String(err.message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>📡 Telecom CDR Analytics</h1>
        <p className="muted">Lawful-interception analytics — analyst sign in</p>
        <input placeholder="Analyst username" value={username}
          onChange={(e) => setUsername(e.target.value)} />
        <input type="password" placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)} />
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {error && <p className="error">{error}</p>}
        <p className="muted small">Demo: <code>agent.alem</code> / <code>insa-demo</code></p>
      </form>
    </div>
  );
}
