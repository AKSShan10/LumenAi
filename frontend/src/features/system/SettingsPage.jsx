import { useEffect, useState } from "react";
import { systemApi } from "./systemApi.js";
import CheckButton from "./CheckButton.jsx";
import ChangePasswordCard from "../auth/ChangePasswordCard.jsx";
import UsersCard from "../auth/UsersCard.jsx";
import DataTable from "../../shared/utils/DataTable.jsx";

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
        <p><CheckButton label="Test Google Drive" check={systemApi.driveCheck} /></p>
        <p><CheckButton label="Test email" check={systemApi.emailCheck} /></p>
      </div>

      <ChangePasswordCard />
      <UsersCard />

      <div className="card">
        <h2>Workflow runs</h2>
        <p className="muted">The latest runs of the AI workflows.</p>
        {!runs ? <p>Loading...</p> : (
          <DataTable rows={runs} empty="No runs yet." columns={[
            { key: "started", title: "Started", render: (r) => asUtc(r.started_at).toLocaleString() },
            { key: "stage", title: "Stage", render: (r) => r.stage.replace("_", " ") },
            { key: "for", title: "For", render: (r) => `#${r.subject_id}` },
            { key: "outcome", title: "Outcome", render: (r) => <span className={`badge ${r.outcome}`}>{r.outcome.replace("_", " ")}</span> },
            { key: "seconds", title: "Seconds" },
            { key: "error", title: "Error", className: "small" },
          ]} />
        )}
      </div>
    </>
  );
}
