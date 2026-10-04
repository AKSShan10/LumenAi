import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import CandidateJoinPage from "./features/interviews/CandidateJoinPage.jsx";
import "./shared/styles/global.css";

// Two kinds of visitors, chosen by the address:
//   /join/<secret>  -> the candidate's page (no login, only the interview)
//   anything else   -> the interviewer's app (login required)
const join = window.location.pathname.match(/^\/join\/([\w-]+)$/);

createRoot(document.getElementById("root")).render(join ? <CandidateJoinPage joinToken={join[1]} /> : <App />);
