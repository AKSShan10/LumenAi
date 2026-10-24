import { useState } from "react";
import AssistantPage from "../assistant/AssistantPage.jsx";
import JobsPage from "./JobsPage.jsx";

// The Jobs page (menu: Jobs) has two views:
//   Chat                    everything is done here: the AI stores documents, writes the job and prepares the post
//   Saved in the database   the jobs, their posts and the company documents (shown only; delete is possible)
export default function JobRequirementsPage() {
  const [view, setView] = useState("chat");

  return (
    <>
      <div className="tabs">
        <button className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}>Chat with the AI</button>
        <button className={view === "saved" ? "active" : ""} onClick={() => setView("saved")}>Saved in the database</button>
      </div>
      {/* Each view is loaded fresh when opened, so a job made in the chat shows up under "Saved in the database". */}
      {view === "chat" ? <AssistantPage /> : <JobsPage />}
    </>
  );
}
