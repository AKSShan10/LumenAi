import { useEffect, useRef, useState } from "react";
import { interviewHelperApi } from "./interviewHelperApi.js";

// The "AI Helper" tab in the interviewer's call (the candidate never sees it).
//   top:    "Suggest questions" (an optional topic) → the newest list: question, the requirement it tests, why,
//           and a model answer behind "Show model answer" (a reference for the interviewer, never a score)
//   bottom: a chat with the helper ("What should I ask about Docker?")
// Everything is saved, so the tab shows the same again after a reload.
// RAG: each answer says which company document it is based on, or that no company document matched.

// Splits "Intro. 1. First 2. Second" (or one item per line) into the intro and the numbered items
function splitList(text) {
  const parts = text.split(/(?:^|\s)(?=\d{1,2}\.\s)/);       // break before "1. ", "2. " ...
  const intro = /^\d{1,2}\.\s/.test(parts[0]) ? "" : parts.shift();
  const items = parts.map((part) => part.replace(/^\d{1,2}\.\s/, "").trim()).filter(Boolean);
  return items.length >= 2 ? { intro: intro.trim(), items } : { intro: text, items: [] };
}

// The helper's chat answer: the intro, then the list one item per line, each with a Copy link
function Answer({ text, copy }) {
  const { intro, items } = splitList(text);
  return (
    <>
      {intro && <div>{intro}</div>}
      {items.length > 0 && (
        <ol className="helper-list">
          {items.map((item, n) => (
            <li key={n}>{item} <button type="button" className="link" onClick={() => copy(item)}>Copy</button></li>
          ))}
        </ol>
      )}
    </>
  );
}

// Which company documents (RAG) an answer is based on, or that none matched
function Sources({ sources }) {
  return sources?.length
    ? <p className="helper-sources small">Based on company document: {sources.join(", ")}</p>
    : <p className="helper-sources small muted">No company document matched: based on the job, the CV and the transcript.</p>;
}

export default function AiHelper({ sessionId, hidden }) {
  const [messages, setMessages] = useState([]);     // every question list and chat message, oldest first
  const [topic, setTopic] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");             // "questions" | "chat" while the AI is working
  const [error, setError] = useState("");
  const [open, setOpen] = useState({});             // which model answers are shown: {"<list id>-<n>": true}
  const chatList = useRef(null);

  // → GET /api/sessions/{id}/helper: what was asked before (also after a reload)
  useEffect(() => {
    interviewHelperApi.history(sessionId).then(setMessages).catch((e) => setError(e.message));
  }, [sessionId]);

  const chat = messages.filter((m) => m.kind === "chat");
  const lists = messages.filter((m) => m.kind === "questions");
  const latest = lists[lists.length - 1];          // only the newest list is shown

  useEffect(() => {                                  // keep the newest chat message in view
    if (chatList.current && !hidden) chatList.current.scrollTop = chatList.current.scrollHeight;
  }, [chat.length, hidden]);

  // On "Suggest questions": the AI suggests up to 8, the backend checks and saves them
  async function suggest(event) {
    event.preventDefault();
    setBusy("questions"); setError("");
    // → POST /api/sessions/{id}/helper/questions
    try { const list = await interviewHelperApi.questions(sessionId, topic.trim()); setMessages((old) => [...old, list]); }
    catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }

  // On "Ask": your message and the helper's answer are added to the chat
  async function ask(event) {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy("chat"); setError("");
    // → POST /api/sessions/{id}/helper/chat
    try { const both = await interviewHelperApi.chat(sessionId, text.trim()); setMessages((old) => [...old, ...both]); setText(""); }
    catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }

  // Copies a question so it can be pasted (for example into the call chat)
  const copy = (words) => navigator.clipboard?.writeText(words).catch(() => {});

  return (
    <div className="ai-helper" hidden={hidden}>
      <form className="ai-helper-ask" onSubmit={suggest}>
        <input value={topic} maxLength="200" placeholder="Topic (optional), e.g. Docker"
               onChange={(e) => setTopic(e.target.value)} />
        <button type="submit" disabled={busy !== ""}>{busy === "questions" ? "Thinking..." : "Suggest questions"}</button>
      </form>
      {error && <p className="error small">{error}</p>}

      <div className="ai-helper-scroll">
        {latest ? (
          <>
          <Sources sources={latest.sources} />
          <ol className="helper-questions">
            {latest.questions.map((q, n) => {
              const key = `${latest.id}-${n}`;
              return (
                <li key={key}>
                  <div className="helper-question">{q.question}</div>
                  <div className="small"><span className="badge">{q.requirement}</span> <span className="muted">{q.why}</span></div>
                  <div className="helper-actions">
                    <button type="button" className="link" onClick={() => setOpen({ ...open, [key]: !open[key] })}>
                      {open[key] ? "Hide model answer" : "Show model answer"}</button>
                    <button type="button" className="link" onClick={() => copy(q.question)}>Copy</button>
                  </div>
                  {open[key] && <p className="helper-answer small">{q.model_answer}
                    {q.source && <span className="helper-source"> Source: {q.source}</span>}</p>}
                </li>
              );
            })}
          </ol>
          </>
        ) : <p className="muted small">Click "Suggest questions" for questions about this candidate, each with a model answer.</p>}

        <h4 className="helper-chat-title">Ask the helper</h4>
        <div className="helper-chat" ref={chatList}>
          {chat.length === 0 && <p className="muted small">For example: "What should I ask about databases?"</p>}
          {chat.map((m) => (
            <div key={m.id} className={`helper-msg ${m.role}`}>
              <b>{m.role === "interviewer" ? "You" : "Helper"}</b>
              {m.role === "helper" ? <><Answer text={m.text} copy={copy} /><Sources sources={m.sources} /></>
                : <div>{m.text}</div>}
            </div>
          ))}
        </div>
      </div>

      <form className="ai-helper-ask" onSubmit={ask}>
        <input value={text} maxLength="1000" placeholder="Ask the helper..." onChange={(e) => setText(e.target.value)} />
        <button type="submit" disabled={busy !== "" || !text.trim()}>{busy === "chat" ? "..." : "Ask"}</button>
      </form>
      <p className="muted small helper-note">The AI only suggests. You decide. The candidate cannot see this tab.</p>
    </div>
  );
}
