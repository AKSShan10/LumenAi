import { useEffect, useState } from "react";
import { talentPoolApi } from "./talentPoolApi.js";

// The public page of the "no more emails" link in a talent pool invitation (/unsubscribe/<token>). No login.
// Opening the page changes nothing: only the button unsubscribes (mail apps sometimes open links by themselves).
export default function UnsubscribePage({ token }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");

  // → GET /api/unsubscribe/{token}: the first name and whether they already unsubscribed
  useEffect(() => { talentPoolApi.unsubscribeInfo(token).then(setInfo).catch((e) => setError(e.message)); }, [token]);

  // → POST /api/unsubscribe/{token}
  async function unsubscribe() {
    try { setInfo(await talentPoolApi.unsubscribe(token)); } catch (e) { setError(e.message); }
  }

  return (
    <div className="login-page">
      <div className="card login">
        <h2>Emails about future openings</h2>
        {error && <p className="error">{error}</p>}
        {info && (info.unsubscribed
          ? <p>You are unsubscribed{info.first_name && `, ${info.first_name}`}. You will not receive more invitations.</p>
          : (
            <>
              <p>{info.first_name && `Hello ${info.first_name}, `}do you want to stop emails about future job openings?</p>
              <button type="button" onClick={unsubscribe}>Unsubscribe</button>
            </>
          ))}
      </div>
    </div>
  );
}
