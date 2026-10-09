import { useState } from "react";
import { authApi } from "./authApi.js";
import { auth } from "../../shared/api/authToken.js";

// Shown on the Settings page: the logged-in interviewer changes their own password.
export default function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError(""); setDone(false);
    if (next !== again) return setError("The two new passwords are not the same.");
    setBusy(true);
    try {
      await authApi.changePassword(current, next);
      setCurrent(""); setNext(""); setAgain(""); setDone(true);
    } catch (e) {
      setError(e.message === "Please check the form fields." ? "The new password needs at least 8 characters." : e.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="card">
      <h2>Your account</h2>
      <p className="muted">{auth.name() || "Interviewer"} · {auth.email()}</p>
      <form onSubmit={submit}>
        <div className="two-columns">
          <label>Current password
            <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
          </label>
          <label>New password <small>(8 characters or more)</small>
            <input type="password" value={next} onChange={(e) => setNext(e.target.value)} minLength="8" autoComplete="new-password" required />
          </label>
          <label>New password again
            <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
          </label>
        </div>
        <button className="secondary" disabled={busy}>{busy ? "Saving..." : "Change password"}</button>
      </form>
      {error && <p className="error">{error}</p>}
      {done && <p className="ok">Your password was changed.</p>}
    </div>
  );
}
