import { useState } from "react";
import AssistantPage from "../assistant/AssistantPage.jsx";
import JobsPage from "./JobsPage.jsx";

// The Job Requirements page has two views:
//   Chat                 talk to the AI: it stores documents, writes the job and prepares the Telegram post
//   Jobs and documents   everything that is saved, with the forms to check and change it by hand
export default function JobRequirementsPage() {
  const [view, setView] = useState("chat");

  return (
    <>
      <div className="tabs">
        <button className={view === "chat" ? "active" : ""} onClick={() => setView("chat")}>Chat with the AI</button>
        <button className={view === "saved" ? "active" : ""} onClick={() => setView("saved")}>Jobs and documents</button>
      </div>
      {/* Each view is loaded fresh when opened, so a job made in the chat shows up under "Jobs and documents". */}
      {view === "chat" ? <AssistantPage /> : <JobsPage />}
    </>
  );
}
