import { useEffect, useRef, useState } from "react";
import { assistantApi } from "./assistantApi.js";
import Icon from "../../shared/utils/Icon.jsx";

// Plain names for the tools, shown under an answer so you can see what the assistant did
const TOOL_NAMES = {
  list_company_documents: "listed the company documents",
  search_company_documents: "searched the company documents",
  add_company_document: "stored a company document",
  save_attached_file_as_document: "stored the attached file",
  write_job_draft: "wrote a job draft",
  save_job: "saved the job",
  list_jobs: "listed the jobs",
  get_job: "read a job",
  prepare_job_post: "prepared the post",
  request_job_approval: "asked you to approve",
  request_job_post: "asked you to post",
  check_blogger_settings: "checked the Blogger login",
};
const EXAMPLES = [
  "Write a job for a backend developer with Python and FastAPI, 3 years experience",
  "Search the company documents for hybrid work",
  "List the jobs",
  "Store the attached file as a company policy",
];

// The assistant: a chat where the AI chooses the tools.
// It can store documents, write and save jobs, and prepare the post.
// It cannot approve a job or post by itself: it asks, and you answer Yes or No here.
// draft = {text}: a message put in the box by a button on the Jobs or Knowledge base tab (nothing is sent by itself).
export default function AssistantPage({ draft }) {
  const [chat, setChat] = useState(null);
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [sent, setSent] = useState(null);       // your message while the assistant is still working
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef(null);
  const bottom = useRef(null);

  useEffect(() => { assistantApi.chat().then(setChat).catch((e) => setError(e.message)); }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [chat, sent]);
  useEffect(() => { if (draft?.text) setText(draft.text); }, [draft]);

  // Runs one assistant API call, shows the chat it returns, and handles the busy and error states
  async function run(action) {
    setError(""); setBusy(true);
    try { setChat(await action()); } catch (e) { setError(e.message); } finally { setBusy(false); setSent(null); }
  }

  // On Send: shows your message at once, clears the box and sends text + file with assistantApi.send
  function send(event) {
    event.preventDefault();
    if (!text.trim() && !file) return;
    const message = text.trim(), attached = file;
    setSent({ content: message || "Please store this file.", attachment_name: attached?.name || "" });
    setText(""); setFile(null);
    if (fileInput.current) fileInput.current.value = "";
    run(() => assistantApi.send(message, attached));
  }

  if (!chat) return <div className="card">{error ? <p className="error">{error}</p> : <p>Loading...</p>}</div>;

  return (
    <div className="card chat">
      <div className="row-between chat-head">
        <p className="info-bar">ⓘ The AI chooses what to do. Approving a job and posting it always wait for your Yes.</p>
        <div className="chat-tools">
          {/* Every chat is kept in the database. Pick one to read it; "Continue this chat" lets you write in it again. */}
          {chat.chats.length > 1 && (
            <select value={chat.chat_id} disabled={busy} title="Your chats"
                    onChange={(e) => run(() => assistantApi.earlier(Number(e.target.value)))}>
              {chat.chats.map((c, index) => (
                <option key={c.id} value={c.id}>
                  {index === 0 ? "Current chat" : new Date(c.started_at).toLocaleDateString()}: {c.title}
                </option>
              ))}
            </select>
          )}
          <button className="secondary" onClick={() => run(assistantApi.newChat)} disabled={busy || (chat.is_current && chat.messages.length === 0)}>+ New chat</button>
        </div>
      </div>
      {!chat.is_current && (
        <p className="warn">This is an earlier chat.{" "}
          <button className="link" onClick={() => run(() => assistantApi.continueChat(chat.chat_id))} disabled={busy}>Continue this chat</button>
          {" "}or{" "}
          <button className="link" onClick={() => run(assistantApi.chat)} disabled={busy}>go back to the current chat</button>.</p>
      )}

      <div className="chat-messages">
        {chat.messages.length === 0 && !sent && (
          <div className="chat-welcome">
            <h3>What would you like to do?</h3>
            <p className="muted">Store a company document, write a job description, or post a job. Click an example to put it in the box.</p>
            <div className="suggestions">
              {EXAMPLES.map((example) => <button key={example} type="button" onClick={() => setText(example)}>{example}</button>)}
            </div>
          </div>
        )}
        {chat.messages.map((message) => (
          <div key={message.id} className={`chat-message ${message.role}`}>
            <div className="bubble">
              {message.content}
              {message.attachment_name && <div className="small"><Icon name="clip" size={14} /> {message.attachment_name}</div>}
            </div>
            {message.tools.length > 0 && (
              <div className="muted small">What I did: {message.tools.map((tool) => TOOL_NAMES[tool] || tool).join(", then ")}</div>
            )}
          </div>
        ))}
        {sent && (
          <div className="chat-message user">
            <div className="bubble">{sent.content}{sent.attachment_name && <div className="small"><Icon name="clip" size={14} /> {sent.attachment_name}</div>}</div>
          </div>
        )}
        {busy && sent && <div className="chat-message assistant"><div className="bubble muted">The assistant is working...</div></div>}

        {/* Questions that wait for your answer. Nothing happens until you click Yes. */}
        {chat.actions.map((action) => (
          <div key={action.id} className="chat-question">
            <b>{action.kind === "approve_job" ? `Approve the job "${action.job_title}"?` : `Post the job "${action.job_title}"?`}</b>
            {action.kind !== "approve_job" && (
              <>
                <p className="muted small">This will be posted, with an "Apply now" link under it:</p>
                <p className="description">{action.text}{"\n\n"}Apply here: {action.apply_url}</p>
              </>
            )}
            <div>
              <button onClick={() => run(() => assistantApi.answer(action.id, true))} disabled={busy}>Yes</button>
              <button className="secondary" onClick={() => run(() => assistantApi.answer(action.id, false))} disabled={busy}>No</button>
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>

      {error && <p className="error">{error}</p>}
      {chat.is_current && file && (
        <p className="file-chip-row">
          <span className="file-chip"><Icon name="clip" size={14} /> {file.name}
            <button type="button" className="link" title="Remove the file" onClick={() => { setFile(null); fileInput.current.value = ""; }}>✕</button></span>
          <span className="muted small">PDF, DOCX or TXT, up to 5 MB</span>
        </p>
      )}
      {chat.is_current && (
      <form onSubmit={send} className="chat-input">
        <label className="attach" title="Attach a PDF, DOCX or TXT file">
          <Icon name="clip" />
          <input type="file" accept=".pdf,.docx,.txt" ref={fileInput} onChange={(e) => setFile(e.target.files[0] || null)} hidden />
        </label>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength="4000" disabled={busy}
               placeholder={file ? `What should I do with ${file.name}?` : "Write a message..."} />
        <button disabled={busy || (!text.trim() && !file)}><Icon name="send" size={16} /> Send</button>
      </form>
      )}
    </div>
  );
}
