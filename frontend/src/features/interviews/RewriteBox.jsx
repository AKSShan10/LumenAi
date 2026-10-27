import { useState } from "react";

// "Write again with AI" with an optional change, for an invitation email (one candidate or Schedule all).
// Empty box: the AI writes a new draft. With a change (typed, or a quick button such as "Shorter"): the AI improves
// the text as it is now on the page, and the same code checks run on the new text.
const QUICK = [["Shorter", "Make it shorter. Keep the date, time, length and the join link."],
               ["Friendlier", "Make it friendlier and warmer, still professional."],
               ["More formal", "Make it more formal."]];

export default function RewriteBox({ busy, writing, onRewrite }) {
  const [change, setChange] = useState("");
  return (
    <div className="rewrite-box">
      <input maxLength="300" value={change} onChange={(e) => setChange(e.target.value)}
             placeholder="What should change? (optional) e.g. shorter, mention that parking is free" />
      <button type="button" className="secondary" disabled={busy} onClick={() => onRewrite(change.trim())}>
        {writing ? "Writing..." : "Write again with AI"}</button>
      <span className="muted small">Quick:</span>
      {QUICK.map(([label, wish]) => (
        <button key={label} type="button" className="secondary small" disabled={busy}
                onClick={() => onRewrite(wish)}>{label}</button>
      ))}
    </div>
  );
}
