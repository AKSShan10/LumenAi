import { useEffect, useState } from "react";
import { auth } from "./shared/api/authToken.js";
import Icon from "./shared/utils/Icon.jsx";
import AppFooter from "./shared/utils/AppFooter.jsx";
import { systemApi } from "./features/system/systemApi.js";
import LoginPage from "./features/auth/LoginPage.jsx";
import SettingsPage from "./features/system/SettingsPage.jsx";
import JobRequirementsPage from "./features/jobs/JobRequirementsPage.jsx";
import CandidatesPage from "./features/candidates/CandidatesPage.jsx";
import InterviewsPage from "./features/interviews/InterviewsPage.jsx";

// The sidebar: [page, label, icon, subtitle]
const MENU = [
  ["dashboard", "Dashboard", "home", "Where every job, CV and interview stands."],
  ["candidates", "Candidates", "people", "Fetch the applications of a job, upload CVs and see who applied."],
  ["interviews", "Interviews", "calendar", "Invitations, live interviews and transcripts."],
  ["jobs", "Job Requirements", "document", "Chat with the AI: store documents, write the job, approve it and post it."],
  ["reports", "Reports", "chart", "Compare candidates and record the decision."],
  ["settings", "Settings", "gear", "Connection checks and the workflow log."],
];

// Each page has its own address: /dashboard, /candidates, /interviews, /jobs, /reports, /settings.
// The page is read from the address, so refresh, the Back button and bookmarks work. No router library needed:
// a click writes the address with history.pushState, and Back/Forward ("popstate") reads it again.
// nginx already sends every address to index.html (try_files in nginx.conf).
function pageFromAddress() {
  const key = window.location.pathname.replace(/^\/+|\/+$/g, "");
  return MENU.some(([page]) => page === key) ? key : "dashboard";    // "/" or an unknown address -> Dashboard
}

// The main interviewer app: login page, or the sidebar with the chosen page; shown by main.jsx
export default function App() {
  const [appName, setAppName] = useState("LumenAI");
  const [loggedIn, setLoggedIn] = useState(Boolean(auth.get()));
  const [page, setPage] = useState(pageFromAddress);

  useEffect(() => {
    // → GET /api/health: shows the app name in the sidebar and tab title
    systemApi.health().then((h) => { setAppName(h.app_name); document.title = h.app_name; }).catch(() => {});
  }, []);

  useEffect(() => {
    // "/" or an unknown address shows the Dashboard: write /dashboard in the address bar too
    if (window.location.pathname !== `/${page}`) window.history.replaceState(null, "", `/${page}`);
    // Runs when Back or Forward is pressed: reads the page from the address bar again
    const onBack = () => setPage(pageFromAddress());
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, []);

  // Opens a sidebar page: writes its address in the address bar (pushState) and shows it
  function openPage(key) {
    if (key !== page) window.history.pushState(null, "", `/${key}`);
    setPage(key);
  }

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
            <button key={key} className={page === key ? "active" : ""} onClick={() => openPage(key)}>
              <Icon name={icon} /> {label}
            </button>
          ))}
        </nav>
        <div className="sidebar-user">
          <span className="avatar">{(auth.name() || auth.email() || "IN").slice(0, 2).toUpperCase()}</span>
          <div><b>{auth.name() || "Interviewer"}</b>{auth.email() && <span className="small">{auth.email()}</span>}<button className="link" onClick={() => { auth.clear(); setLoggedIn(false); }}>Log out</button></div>
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
          {page === "interviews" && <InterviewsPage />}
          {/* Placeholder: each feature replaces this card with its real page. */}
          {!["settings", "jobs", "candidates", "interviews"].includes(page) && <div className="card"><p className="muted">This screen is not built yet.</p></div>}
        </main>

        <AppFooter appName={appName} />
      </div>
    </div>
  );
}
