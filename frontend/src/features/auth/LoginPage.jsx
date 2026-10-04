import { useState } from "react";
import { authApi } from "./authApi.js";
import { auth } from "../../shared/api/authToken.js";
import AppFooter from "../../shared/utils/AppFooter.jsx";

export default function LoginPage({ appName, onDone }) {
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const { token } = await authApi.login(passcode);
      auth.set(token);
      onDone();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="login-page">
      <form className="card login" onSubmit={submit}>
        <h1>{appName}</h1>
        <p className="muted">Interviewer login</p>
        <label>Passcode
          <input type="password" value={passcode} onChange={(e) => setPasscode(e.target.value)} required autoFocus />
        </label>
        {error && <p className="error">{error}</p>}
        <button>Log in</button>
      </form>
      <AppFooter appName={appName} />
    </div>
  );
}
