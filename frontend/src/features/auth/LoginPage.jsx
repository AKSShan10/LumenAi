import { useEffect, useState } from "react";
import { authApi } from "./authApi.js";
import { auth } from "../../shared/api/authToken.js";
import AppFooter from "../../shared/utils/AppFooter.jsx";

// The login page. The very first time, when no account exists yet, it shows "Create the interviewer account"
// instead. The account is saved in the database; the password is saved as a hash, never as it was typed.
export default function LoginPage({ appName, onDone }) {
  const [firstRun, setFirstRun] = useState(null);     // null = still asking the backend
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");             // the password typed a second time (first run only)
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    authApi.status().then((answer) => setFirstRun(!answer.has_account)).catch((e) => { setFirstRun(false); setError(e.message); });
  }, []);

  // On submit: creates the first account (setup) or logs in, then keeps the token and opens the app
  async function submit(event) {
    event.preventDefault();
    setError("");
    if (firstRun && password !== again) return setError("The two passwords are not the same.");
    setBusy(true);
    try {
      const answer = firstRun ? await authApi.setup(fullName.trim(), email.trim(), password)
                              : await authApi.login(email.trim(), password);
      // → keeps the backend's login token in sessionStorage for later requests
      auth.set(answer.token, answer.email, answer.full_name);
      onDone();
    } catch (e) {
      setError(firstRun && e.message === "Please check the form fields."
        ? "Type your name, a full email address and a password of at least 8 characters." : e.message);
    } finally { setBusy(false); }
  }

  if (firstRun === null) return <div className="login-page"><div className="card login"><p>Loading...</p></div></div>;

  return (
    <div className="login-page">
      <form className="card login" onSubmit={submit}>
        <h1>{appName}</h1>
        <p className="muted">{firstRun ? "Welcome. Create the interviewer account to start." : "Interviewer login"}</p>
        {firstRun && (
          <label>Full name
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength="120" autoComplete="name" required autoFocus />
          </label>
        )}
        <label>Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com"
                 autoComplete="username" required autoFocus={!firstRun} />
        </label>
        <label>Password {firstRun && <small>(8 characters or more)</small>}
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={firstRun ? 8 : 1}
                 autoComplete={firstRun ? "new-password" : "current-password"} required />
        </label>
        {firstRun && (
          <label>Password again
            <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
          </label>
        )}
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>{firstRun ? "Create account" : "Log in"}</button>
      </form>
      <AppFooter appName={appName} />
    </div>
  );
}
