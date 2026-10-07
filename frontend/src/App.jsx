import { useEffect, useState } from "react";
import { auth } from "./shared/api/authToken.js";
import Icon from "./shared/utils/Icon.jsx";
import AppFooter from "./shared/utils/AppFooter.jsx";
import { systemApi } from "./features/system/systemApi.js";
import LoginPage from "./features/auth/LoginPage.jsx";
import SettingsPage from "./features/system/SettingsPage.jsx";
import JobRequirementsPage from "./features/jobs/JobRequirementsPage.jsx";
import CandidatesPage from "./features/candidates/CandidatesPage.jsx";

// The sidebar: [page, label, icon, subtitle]
const MENU = [
  ["dashboard", "Dashboard", "home", "Where every job, CV and interview stands."],
  ["candidates", "Candidates", "people", "Fetch the applications of a job, upload CVs and see who applied."],
  ["interviews", "Interviews", "calendar", "Invitations, live interviews and transcripts."],
  ["jobs", "Job Requirements", "document", "Chat with the AI: store documents, write the job, approve it and post it."],
  ["reports", "Reports", "chart", "Compare candidates and record the decision."],
  ["settings", "Settings", "gear", "Connection checks and the workflow log."],
];

// The interviewer's app. Simple navigation with useState: no router library needed.
export default function App() {
  const [appName, setAppName] = useState("LumenAI");
  const [loggedIn, setLoggedIn] = useState(Boolean(auth.get()));
  const [page, setPage] = useState("dashboard");

  useEffect(() => {
    systemApi.health().then((h) => { setAppName(h.app_name); document.title = h.app_name; }).catch(() => {});
  }, []);

  if (!loggedIn) return <LoginPage appName={appName} onDone={() => setLoggedIn(true)} />;

  const [, title, , subtitle] = MENU.find(([key]) => key === page);

  return (
    <div className="shell">
      {/* The sidebar always fills the window. Only the page on the right scrolls. */}
      <aside className="sidebar">
        <div className="brand">
          <b>{appName}</b>
          <span>Recruitment and interview intelligence</span>
        </div>
        <nav>
          {MENU.map(([key, label, icon]) => (
            <button key={key} className={page === key ? "active" : ""} onClick={() => setPage(key)}>
              <Icon name={icon} /> {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-user">
          <span className="avatar">IN</span>
          <div><b>Interviewer</b><button className="link" onClick={() => { auth.clear(); setLoggedIn(false); }}>Log out</button></div>
        </div>
      </aside>

      <div className="content">
        {/* header: the page title */}
        <header className="app-header">
          <div>
            <h1>{title}</h1>
            <p className="muted">{subtitle}</p>
          </div>
        </header>

        <main>
          {page === "settings" && <SettingsPage />}
          {page === "jobs" && <JobRequirementsPage />}
          {page === "candidates" && <CandidatesPage />}
          {/* Placeholder: each feature replaces this card with its real page. */}
          {!["settings", "jobs", "candidates"].includes(page) && <div className="card"><p className="muted">This screen is not built yet.</p></div>}
        </main>

        <AppFooter appName={appName} />
      </div>
    </div>
  );
}
