import { useEffect, useState } from "react";
import AssistantPage from "../assistant/AssistantPage.jsx";
import JobsPage from "./JobsPage.jsx";
import CompanyDocumentsPanel from "../job_library/CompanyDocumentsPanel.jsx";
import { jobsApi } from "./jobsApi.js";
import { companyDocumentsApi } from "../job_library/companyDocumentsApi.js";

// The Jobs page (menu: Jobs) has three tabs:
//   Chat with the AI   everything is done here: the AI stores documents, writes the job and prepares the post
//   Jobs               the saved jobs and their posts (shown only; delete is possible)
//   Knowledge base     the company documents the AI reads before it writes (RAG): shown, searched, removed
export default function JobRequirementsPage() {
  const [view, setView] = useState("chat");
  const [draft, setDraft] = useState({ text: "" });          // a message put in the chat box by a button
  const [counts, setCounts] = useState({ jobs: null, documents: null });

  // The numbers on the tabs: read again when a tab is opened, and after a delete
  function loadCounts() {
    jobsApi.list().then((list) => setCounts((c) => ({ ...c, jobs: list.length }))).catch(() => {});
    companyDocumentsApi.list().then((list) => setCounts((c) => ({ ...c, documents: list.length }))).catch(() => {});
  }
  useEffect(loadCounts, [view]);

  // Opens the chat with a message ready in the box (for example "Approve job #3"); the interviewer clicks Send
  function openChat(text = "") {
    setDraft({ text });                                        // a new object, so the same text works twice
    setView("chat");
  }

  const tab = (key, label, count) => (
    <button className={view === key ? "active" : ""} onClick={() => setView(key)}>
      {label}{count !== null && count !== undefined && <span className="count">{count}</span>}
    </button>
  );

  return (
    <>
      <div className="tabs">
        {tab("chat", "Chat with the AI")}
        {tab("jobs", "Jobs", counts.jobs)}
        {tab("knowledge", "Knowledge base", counts.documents)}
      </div>
      {/* Each tab is loaded fresh when opened, so a job or document made in the chat shows up at once. */}
      {view === "chat" && <AssistantPage draft={draft} />}
      {view === "jobs" && <JobsPage onOpenChat={openChat} onChanged={loadCounts} />}
      {view === "knowledge" && <CompanyDocumentsPanel onOpenChat={openChat} onChanged={loadCounts} />}
    </>
  );
}
