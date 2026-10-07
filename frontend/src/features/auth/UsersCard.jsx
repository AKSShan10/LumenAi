import { useEffect, useState } from "react";
import { authApi } from "./authApi.js";
import { auth } from "../../shared/api/authToken.js";
import ConfirmDialog from "../../shared/utils/ConfirmDialog.jsx";

// Shown on the Settings page: the interviewer accounts, and a form to register one more.
// Only someone who is logged in can register an account; there is no public sign-up page.
export default function UsersCard() {
  const [users, setUsers] = useState([]);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [toRemove, setToRemove] = useState(null);     // the account the yes / no pop-up asks about
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const load = () => authApi.users().then(setUsers).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function add(event) {
    event.preventDefault();
    setError(""); setNote(""); setBusy(true);
    try {
      const user = await authApi.addUser(fullName.trim(), email.trim(), password);
      setNote(`The account of ${user.full_name} was created. Give them the email and the password; they can change the password after logging in.`);
      setFullName(""); setEmail(""); setPassword("");
      await load();
    } catch (e) {
      setError(e.message === "Please check the form fields."
        ? "Type a name, a full email address and a password of at least 8 characters." : e.message);
    } finally { setBusy(false); }
  }

  async function remove() {
    const user = toRemove;
    setToRemove(null); setError(""); setNote("");
    try { await authApi.removeUser(user.id); await load(); } catch (e) { setError(e.message); }
  }

  return (
    <div className="card">
      <h2>Interviewer accounts <small className="muted">({users.length})</small></h2>
      <table>
        <thead><tr><th>Name</th><th>Email</th><th>Created</th><th></th></tr></thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.full_name}{user.email === auth.email() && <span className="muted small"> (you)</span>}</td>
              <td className="small">{user.email}</td>
              <td className="small">{new Date(user.created_at).toLocaleDateString()}</td>
              <td>{user.email !== auth.email() && <button className="link" onClick={() => setToRemove(user)}>Remove</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="section">
        <h3>Register a new account</h3>
        <form onSubmit={add}>
          <div className="two-columns">
            <label>Full name
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength="120" required />
            </label>
            <label>Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@company.com" autoComplete="off" required />
            </label>
            <label>First password <small>(8 characters or more)</small>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength="8" autoComplete="new-password" required />
            </label>
          </div>
          <button className="secondary" disabled={busy}>{busy ? "Creating..." : "Create account"}</button>
        </form>
      </div>
      {error && <p className="error">{error}</p>}
      {note && <p className="ok">{note}</p>}

      {toRemove && (
        <ConfirmDialog question={`Remove the account of ${toRemove.full_name || toRemove.email}?`}
                       detail="They will not be able to log in any more. Jobs, candidates and chats are not deleted."
                       onYes={remove} onNo={() => setToRemove(null)} />
      )}
    </div>
  );
}
