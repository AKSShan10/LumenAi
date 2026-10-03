import { useState } from "react";

// A button that runs a setup check and shows the answer in plain words (green = ok, red = what to fix).
export default function CheckButton({ label, check }) {
  const [result, setResult] = useState(null);

  async function run() {
    setResult({ ok: null, message: "Checking..." });
    try {
      setResult(await check());
    } catch (e) {
      setResult({ ok: false, message: e.message });
    }
  }

  return (
    <span className="check">
      <button type="button" className="secondary" onClick={run}>{label}</button>
      {result && (
        <span className={result.ok ? "ok" : result.ok === false ? "error" : "muted"}>
          {result.provider && <span className="muted">{result.provider}{result.model ? ` · ${result.model}` : ""} — </span>}
          {result.message}
        </span>
      )}
    </span>
  );
}
