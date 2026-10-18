import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import CandidateJoinPage from "./features/interviews/CandidateJoinPage.jsx";
import InterviewRoomPage from "./features/interviews/InterviewRoomPage.jsx";
import InterviewAnalysisPage from "./features/qa_analysis/InterviewAnalysisPage.jsx";
import AssessmentReportPage from "./features/assessments/AssessmentReportPage.jsx";
import "./shared/styles/global.css";

// Chosen by the address:
//   /join/<secret>         -> the candidate's page (no login, only the interview)
//   /interview-room/<id>   -> the interviewer's call in its own tab (login copied from the tab that opened it)
//   /interview-analysis/<id> -> the Q&A analysis and transcript of an interview in its own tab (same login copy)
//   /assessment-report/<id>  -> the assessment report of a candidate in its own tab (same login copy)
//   anything else          -> the interviewer's app (login required)
const join = window.location.pathname.match(/^\/join\/([\w-]+)$/);
const room = window.location.pathname.match(/^\/interview-room\/(\d+)$/);
const analysis = window.location.pathname.match(/^\/interview-analysis\/(\d+)$/);
const report = window.location.pathname.match(/^\/assessment-report\/(\d+)$/);

createRoot(document.getElementById("root")).render(
  join ? <CandidateJoinPage joinToken={join[1]} />
    : room ? <InterviewRoomPage sessionId={Number(room[1])} />
      : analysis ? <InterviewAnalysisPage sessionId={Number(analysis[1])} />
        : report ? <AssessmentReportPage candidateId={Number(report[1])} />
          : <App />,
);
