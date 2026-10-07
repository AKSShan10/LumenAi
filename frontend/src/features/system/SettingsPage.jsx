import { useEffect, useState } from "react";
import { systemApi } from "./systemApi.js";
import CheckButton from "./CheckButton.jsx";

// The log stores UTC times without a time zone; add "Z" so the browser shows local time.
const asUtc = (text) => new Date(/Z|[+-]\d\d:\d\d$/.test(text) ? text : text + "Z");

// Setup checks and the log of AI workflow runs. Keys are set in the .env file, never on this page.
export default function SettingsPage() {
  const [runs, setRuns] = useState(null);

  useEffect(() => { systemApi.workflowRuns().then(setRuns).catch(() => setRuns([])); }, []);

  return (
    <>
      <div className="card">
        <h2>Connection checks</h2>
        <p className="muted">Each check makes one small test call and says in plain words what to fix. Keys live in the .env file.</p>
        <p><CheckButton label="Test AI connection" check={systemApi.llmCheck} /></p>
        <p><CheckButton label="Test job posting" check={systemApi.postingCheck} /></p>
      </div>

      <div className="card">
        <h2>Workflow runs</h2>
        <p className="muted">The latest runs of the AI workflows.</p>
        {!runs ? <p>Loading...</p> : runs.length === 0 ? <p className="muted">No runs yet.</p> : (
          <table>
            <thead><tr><th>Started</th><th>Stage</th><th>For</th><th>Outcome</th><th>Seconds</th><th>Error</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{asUtc(r.started_at).toLocaleString()}</td>
                  <td>{r.stage.replace("_", " ")}</td>
                  <td>#{r.subject_id}</td>
                  <td><span className={`badge ${r.outcome}`}>{r.outcome.replace("_", " ")}</span></td>
                  <td>{r.seconds}</td>
                  <td className="small">{r.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
