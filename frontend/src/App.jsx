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
import ReportsPage from "./features/assessments/ReportsPage.jsx";
import TalentPoolPage from "./features/talent_pool/TalentPoolPage.jsx";
import DashboardPage from "./features/dashboard/DashboardPage.jsx";
import InterviewAnalysisPage from "./features/qa_analysis/InterviewAnalysisPage.jsx";
import AssessmentReportPage from "./features/assessments/AssessmentReportPage.jsx";
import { navigate } from "./shared/utils/navigate.js";

// The sidebar: [page, label, icon, subtitle], in the order of the hiring process:
// write and post the job → collect and screen CVs → interview → report and decide → talent pool
const MENU = [
  ["dashboard", "Dashboard", "home", "Where every job, CV and interview stands."],
  ["jobs", "Jobs", "document", "Chat with the AI: store documents, write the job, approve it and post it."],
  ["candidates", "Candidates", "people", "Fetch the applications of a job, upload CVs and see who applied."],
  ["interviews", "Interviews", "calendar", "Schedule interviews, send invitations, run the calls and read the transcripts."],
  ["reports", "Reports", "chart", "Compare candidates and record the decision."],
  ["talent-pool", "Talent Pool", "star", "Keep good past candidates and invite them to new jobs that fit."],
  ["settings", "Settings", "gear", "Connection checks and the workflow log."],
];

// Each page has its own address: /dashboard, /candidates, /interviews, /jobs, /reports, /talent-pool, /settings.
// The page is read from the address, so refresh, the Back button and bookmarks work. No router library needed:
// a click writes the address with history.pushState, and Back/Forward ("popstate") reads it again.
// nginx already sends every address to index.html (try_files in nginx.conf).
// Two detail pages open inside the app too, under the menu page they belong to (breadcrumb "Interviews › ..."):
//   /interview-analysis/<interview id>   the Q&A analysis of one interview      (menu: Interviews)
//   /assessment-report/<candidate id>    the assessment report of one candidate (menu: Reports)
const DETAILS = [
  [/^interview-analysis\/(\d+)$/, "interviews", "Q&A analysis"],
  [/^assessment-report\/(\d+)$/, "reports", "Assessment report"],
];

// Reads the address: {page, detail} — detail = {kind, id, title} on a detail page, else null
function routeFromAddress() {
  const key = window.location.pathname.replace(/^\/+|\/+$/g, "");
  for (const [pattern, page, title] of DETAILS) {
    const found = key.match(pattern);
    if (found) return { page, detail: { kind: page === "interviews" ? "analysis" : "report", id: Number(found[1]), title } };
  }
  return { page: MENU.some(([page]) => page === key) ? key : "dashboard", detail: null };    // "/" or unknown -> Dashboard
}

// The main interviewer app: login page, or the sidebar with the chosen page; shown by main.jsx
export default function App() {
  const [appName, setAppName] = useState("LumenAI");
  const [loggedIn, setLoggedIn] = useState(Boolean(auth.get()));
  const [route, setRoute] = useState(routeFromAddress);
  const { page, detail } = route;

  useEffect(() => {
    // → GET /api/health: shows the app name in the sidebar and tab title
    systemApi.health().then((h) => { setAppName(h.app_name); document.title = h.app_name; }).catch(() => {});
  }, []);

  useEffect(() => {
    // "/" or an unknown address shows the Dashboard: write /dashboard in the address bar too
    if (!detail && window.location.pathname !== `/${page}`) window.history.replaceState(null, "", `/${page}`);
    // Runs when Back or Forward is pressed (or navigate() is called): reads the page from the address bar again
    const onBack = () => { setRoute(routeFromAddress()); document.querySelector(".content")?.scrollTo(0, 0); };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, []);

  // Opens a sidebar page: writes its address in the address bar (pushState) and shows it
  function openPage(key) {
    if (key !== page || detail) navigate(`/${key}`);
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
          {detail ? (                                 // a detail page: the breadcrumb leads back to its menu page
            <div>
              <nav className="breadcrumb" aria-label="Breadcrumb">
                <a href={`/${page}`} onClick={(e) => { e.preventDefault(); openPage(page); }}>{title}</a>
                <span aria-hidden="true">›</span><span>{detail.title}</span>
              </nav>
              <h1>{detail.title}</h1>
            </div>
          ) : (
            <div>
              <h1>{title}</h1>
              <p className="muted">{subtitle}</p>
            </div>
          )}
        </header>

        <main>
          {detail?.kind === "analysis" && <InterviewAnalysisPage key={detail.id} sessionId={detail.id} />}
          {detail?.kind === "report" && <AssessmentReportPage key={detail.id} candidateId={detail.id} />}
          {!detail && page === "dashboard" && <DashboardPage onOpen={openPage} />}
          {!detail && page === "settings" && <SettingsPage />}
          {!detail && page === "jobs" && <JobRequirementsPage />}
          {!detail && page === "candidates" && <CandidatesPage />}
          {!detail && page === "interviews" && <InterviewsPage />}
          {!detail && page === "reports" && <ReportsPage />}
          {!detail && page === "talent-pool" && <TalentPoolPage />}
          {/* Placeholder: each feature replaces this card with its real page. */}
          {!["dashboard", "settings", "jobs", "candidates", "interviews", "reports", "talent-pool"].includes(page) && <div className="card"><p className="muted">This screen is not built yet.</p></div>}
        </main>

        <AppFooter appName={appName} />
      </div>
    </div>
  );
}
