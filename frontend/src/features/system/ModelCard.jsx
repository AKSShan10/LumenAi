import { useEffect, useState } from "react";
import { systemApi } from "./systemApi.js";
import CheckButton from "./CheckButton.jsx";

// The "AI model" card on Settings: choose one of the models allowed in .env (LLM_MODEL_CHOICES).
// The next AI call uses it, no restart. Useful when a model is busy (HTTP 503). The API key stays in .env.
export default function ModelCard() {
  const [info, setInfo] = useState(null);
  const [chosen, setChosen] = useState("");
  const [message, setMessage] = useState(null);

  // → GET /api/llm-model
  useEffect(() => {
    systemApi.llmModel().then((found) => { setInfo(found); setChosen(found.model); })
      .catch((e) => setMessage({ ok: false, text: e.message }));
  }, []);

  // → PUT /api/llm-model
  async function save() {
    setMessage(null);
    try {
      const saved = await systemApi.setLlmModel(chosen);
      setInfo(saved);
      setMessage({ ok: true, text: `Saved. The next AI call uses ${saved.model}. Click Test AI connection to check it.` });
    } catch (e) { setMessage({ ok: false, text: e.message }); }
  }

  if (!info) return message ? <div className="card"><p className="error">{message.text}</p></div> : null;
  return (
    <div className="card">
      <h2>AI model</h2>
      <p className="muted">Choose the Gemini model for every AI step. The list comes from LLM_MODEL_CHOICES in the .env
        file; the default is {info.default}. If a model is busy, choose another one here.</p>
      <div className="pool-filters">
        <select value={chosen} onChange={(e) => setChosen(e.target.value)} aria-label="AI model">
          {info.choices.map((name) => (
            <option key={name} value={name}>{name}{name === info.default ? " (default)" : ""}</option>
          ))}
        </select>
        <button type="button" onClick={save} disabled={chosen === info.model}>Save model</button>
        <CheckButton label="Test AI connection" check={systemApi.llmCheck} />
      </div>
      <p className="small muted">In use now: <b>{info.model}</b></p>
      {message && <p className={message.ok ? "ok small" : "error small"}>{message.text}</p>}
    </div>
  );
}
