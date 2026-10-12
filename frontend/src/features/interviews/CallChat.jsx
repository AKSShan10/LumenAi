import { useEffect, useRef, useState } from "react";

// The chat inside the video call, for the interviewer and the candidate: text and links.
// load(after) gets the messages after a message id; send(text) sends one. The page asks for new messages every
// 2 seconds. The text is shown as plain text (React escapes it); web addresses become links that open in a new tab.
//
// Like Google Meet: the panel is closed until the Chat button is clicked, and the × closes it again.
// While it is closed, a new message from the other person
//   - shows a small pop-up for a few seconds (click it to open the chat),
//   - is counted on the Chat button (onUnread) and in the browser tab title, e.g. "(2) Interview".
const LOOK_AGAIN_MS = 2000;
const POPUP_MS = 6000;
const LINK = /(https?:\/\/[^\s<>"]+)/g;

function withLinks(text) {
  return text.split(LINK).map((part, index) => (
    index % 2 === 1
      ? <a key={index} href={part} target="_blank" rel="noopener noreferrer">{part}</a>
      : <span key={index}>{part}</span>
  ));
}

// Your own messages say "You"; the other person's show their name (the backend saves it with each message).
const whoIs = (m, me) => (m.sender === me ? "You" : m.sender_name);

export default function CallChat({ me, load, send, open, onUnread, onOpen, onClose }) {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [seen, setSeen] = useState(0);              // the newest message id the person has seen
  const [popup, setPopup] = useState(null);         // the newest message, shown for a few seconds while closed
  const newest = useRef(0);
  const popped = useRef(0);                         // the newest message id already shown as a pop-up
  const list = useRef(null);
  const input = useRef(null);
  const title = useRef(document.title);             // the tab title without the count

  function look() {
    return load(newest.current).then((more) => {
      if (more.length === 0) return;
      newest.current = Math.max(newest.current, more[more.length - 1].id);
      setMessages((old) => {                       // two looks can overlap (sending + every 2 s): add each message once
        const last = old.length ? old[old.length - 1].id : 0;
        return [...old, ...more.filter((m) => m.id > last)];
      });
    });
  }

  useEffect(() => {
    look().catch(() => {});
    const timer = setInterval(() => look().catch(() => {}), LOOK_AGAIN_MS);
    const tabTitle = title.current;
    return () => { clearInterval(timer); document.title = tabTitle; };
  }, []);                                            // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                                  // open: everything is seen, scroll to the newest, ready to type
    if (open) {
      setSeen(newest.current);
      setPopup(null);
      if (list.current) list.current.scrollTop = list.current.scrollHeight;
    }
  }, [open, messages]);

  useEffect(() => { if (open && input.current) input.current.focus(); }, [open]);

  const unread = open ? 0 : messages.filter((m) => m.id > seen && m.sender !== me).length;
  useEffect(() => {                                  // the count on the Chat button and in the tab title
    onUnread(unread);
    document.title = unread ? `(${unread}) ${title.current}` : title.current;
  }, [unread]);                                      // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                                  // closed: a pop-up for the other person's newest message
    if (open) return;
    const last = [...messages].reverse().find((m) => m.sender !== me);
    if (!last || last.id <= seen || last.id <= popped.current) return;
    popped.current = last.id;
    setPopup(last);
  }, [messages, open, seen]);                        // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                                  // the pop-up goes away by itself
    if (!popup) return undefined;
    const timer = setTimeout(() => setPopup(null), POPUP_MS);
    return () => clearTimeout(timer);
  }, [popup]);

  async function submit(event) {
    event.preventDefault();
    if (!text.trim()) return;
    setError("");
    try {
      await send(text.trim());
      setText("");
      await look();
    } catch (e) { setError(e.message); }
  }

  return (
    <>
      {popup && !open && (
        <button type="button" className="chat-popup" onClick={onOpen} title="Open the chat">
          <b>{whoIs(popup, me)}</b>
          <span>{popup.text.length > 120 ? `${popup.text.slice(0, 120)}...` : popup.text}</span>
        </button>
      )}
      <aside className="call-chat" hidden={!open}>
        <div className="call-chat-head">
          <b>In-call messages</b>
          <button type="button" className="call-chat-close" onClick={onClose} aria-label="Close the chat" title="Close">×</button>
        </div>
        <div className="call-chat-list" ref={list}>
          {messages.length === 0 && <p className="muted small">No messages yet. You can share text and links here.</p>}
          {messages.map((m) => (
            <div key={m.id} className={`call-chat-msg ${m.sender === me ? "mine" : ""}`}>
              <div className="call-chat-who">
                {whoIs(m, me)}
                {" · "}{new Date(m.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </div>
              <div className="call-chat-text">{withLinks(m.text)}</div>
            </div>
          ))}
        </div>
        {error && <p className="error small">{error}</p>}
        <form className="call-chat-form" onSubmit={submit}>
          <input id={`call-chat-${me}`} ref={input} value={text} maxLength="1000" placeholder="Type a message or paste a link"
                 onChange={(e) => setText(e.target.value)} />
          <button type="submit" disabled={!text.trim()}>Send</button>
        </form>
      </aside>
    </>
  );
}
