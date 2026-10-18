import { useEffect, useState } from "react";
import { auth } from "../../shared/api/authToken.js";
import { assessmentsApi } from "./assessmentsApi.js";

// The assessment report of one candidate, in its own browser tab (/assessment-report/<candidate id>), opened from
// the Reports page. The tab gets a copy of the login from the tab that opened it.
//   scores (CV, interview, overall) · summary · strengths and weaknesses with their proof · evidence gaps ·
//   areas to explore · the interviewer's decision · Export PDF (the browser's print: only the report is printed)
//   · Download HTML (the same report as one HTML file that opens in any browser)
// ?start=1 (from "Create assessment"): the tab starts the assessment itself and shows the progress.
// The AI writes the report; the decision is always made by the interviewer.
const LOOK_AGAIN_MS = 3000;            // while the assessment runs, the page asks again every 3 seconds
const DECISIONS = [["hire", "Hire"], ["hold", "Hold"], ["reject", "Reject"]];

// The colour of a score: green 75 and above, amber 50 and above, red below 50
const tone = (value) => (value === null || value === undefined ? "" : value >= 75 ? "good" : value >= 50 ? "fair" : "weak");

// Makes text safe to put inside HTML ("<" and "&" in a CV would otherwise break the file)
const safe = (text) => String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// The report as one self-contained HTML file (styles inside), for "Download HTML": opens in any browser, offline
function reportHtml(report) {
  const weight = report.cv_weight;
  const list = (items) => (items.length
    ? `<ul>${items.map((i) => `<li>${safe(i.text)}<div class="quote">"${safe(i.quote)}" · ${safe(i.source)}</div></li>`).join("")}</ul>`
    : "<p class=\"muted\">None proven with a quote.</p>");
  const decision = report.decision === "pending" ? "Pending"
    : `${report.decision[0].toUpperCase()}${report.decision.slice(1)}${report.decision_note ? ` · ${safe(report.decision_note)}` : ""}`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Assessment report · ${safe(report.candidate_name)}</title>
<style>
  body { font-family: system-ui, sans-serif; color: #1c2434; max-width: 900px; margin: 32px auto; padding: 0 16px; line-height: 1.5; }
  h1 { font-size: 22px; margin-bottom: 0; } h2 { font-size: 16px; margin: 24px 0 8px; border-bottom: 1px solid #e3e7ef; }
  .muted, .quote { color: #5f6878; font-size: 13px; } .scores { display: flex; gap: 12px; margin-top: 16px; }
  .score { border: 1px solid #e3e7ef; border-radius: 10px; padding: 10px 16px; } .score b { display: block; font-size: 24px; }
  .gap { display: inline-block; background: #fbdcd9; color: #b3261e; border-radius: 10px; padding: 2px 8px; margin: 0 4px 4px 0; font-size: 13px; }
  li { margin-bottom: 8px; }
</style></head><body>
<h1>Assessment report · ${safe(report.candidate_name)}</h1>
<p class="muted">${safe(report.job_title)} · ${safe(new Date(report.updated_at).toLocaleString())}</p>
<div class="scores">
  <div class="score">CV score (${weight} %)<b>${report.cv_score}</b></div>
  <div class="score">Interview score (${100 - weight} %)<b>${report.interview_score}</b></div>
  <div class="score">Overall score<b>${report.overall_score}</b></div>
</div>
<h2>Summary</h2><p>${safe(report.summary)}</p>
<h2>Strengths</h2>${list(report.strengths)}
<h2>Weaknesses</h2>${list(report.weaknesses)}
<h2>Evidence gaps</h2>${report.evidence_gaps.length ? report.evidence_gaps.map((g) => `<span class="gap">${safe(g)}</span>`).join("")
    : "<p>None: every requirement has some proof.</p>"}
<h2>Areas to explore</h2><ul>${report.recommended_areas.map((a) => `<li><b>${safe(a.area)}</b><div class="quote">${safe(a.why)}</div></li>`).join("")}</ul>
<h2>Decision</h2><p><b>${decision}</b></p>
<p class="muted">Every strength and weakness has a quote checked against the CV or the interview transcript. The AI wrote
the report; the decision was made by the interviewer.</p>
</body></html>`;
}

// "Download HTML": saves the report file (made in the browser from the data on the page; nothing new is asked)
function downloadHtml(report) {
  const file = new Blob([reportHtml(report)], { type: "text/html" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(file);
  link.download = `assessment-${(report.candidate_name || "candidate").replace(/\W+/g, "-")}.html`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// Strengths or weaknesses: the sentence, then the proof (the quote and where it is from)
function EvidenceList({ items, empty }) {
  if (!items.length) return <p className="muted small">{empty}</p>;
  return (
    <ul className="evidence-list">
      {items.map((item, n) => (
        <li key={n}>{item.text}
          <div className="small muted">"{item.quote}" · {item.source}</div></li>
      ))}
    </ul>
  );
}

// The decision card: the interviewer chooses hire, hold or reject and may add a note (only the result is printed)
function DecisionCard({ report, onSaved }) {
  const [decision, setDecision] = useState(report.decision === "pending" ? "" : report.decision);
  const [note, setNote] = useState(report.decision_note || "");
  const [message, setMessage] = useState(null);

  // → PUT /api/candidates/{id}/assessment/decision ("pending" takes the decision back)
  async function save(choice) {
    setMessage(null);
    try {
      onSaved(await assessmentsApi.decide(report.candidate_id, choice, note));
      setMessage({ ok: true, text: choice === "pending" ? "The decision was taken back." : "The decision was saved." });
      if (choice === "pending") setDecision("");
    } catch (e) { setMessage({ ok: false, text: e.message }); }
  }

  const decided = report.decision !== "pending";
  return (
    <div className="card report-decision">
      <h3>Decision</h3>
      <p className="print-only"><b>{decided ? DECISIONS.find(([key]) => key === report.decision)?.[1] : "Pending"}</b>
        {report.decision_note && ` · ${report.decision_note}`}</p>
      <div className="no-print">
        <div className="decision-choices">
          {DECISIONS.map(([key, label]) => (
            <label key={key} className={`decision-choice ${decision === key ? `chosen ${key}` : ""}`}>
              <input type="radio" name="decision" value={key} checked={decision === key}
                     onChange={() => setDecision(key)} /> {label}
            </label>
          ))}
        </div>
        <textarea rows="3" maxLength="1000" placeholder="Note (optional), e.g. why, or the next step"
                  value={note} onChange={(e) => setNote(e.target.value)} />
        <button type="button" onClick={() => save(decision)} disabled={!decision}>Save decision</button>
        {decided && <button type="button" className="secondary" onClick={() => save("pending")}>Take back</button>}
        {message && <p className={message.ok ? "ok small" : "error small"}>{message.text}</p>}
      </div>
      {decided && <p className="small muted">Decided by {report.decided_by}
        {report.decided_at && ` on ${new Date(report.decided_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`}</p>}
      <p className="small muted">The AI only writes the report. The decision is yours.</p>
    </div>
  );
}

export default function AssessmentReportPage({ candidateId }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const running = report?.status === "running";

  // When the tab opens: the report; with ?start=1 a new assessment is started if there is none yet
  useEffect(() => {
    if (!auth.get()) return;
    const autoStart = new URLSearchParams(window.location.search).get("start") === "1";
    window.history.replaceState(null, "", window.location.pathname);   // a reload does not start it again
    // → GET /api/candidates/{id}/assessment
    assessmentsApi.get(candidateId).then((found) => {
      setReport(found);
      document.title = `Assessment: ${found.candidate_name || "candidate"}`;
      if (autoStart && found.status === "not_started") start();
    }).catch((e) => setError(e.message));
  }, [candidateId]);                                 // eslint-disable-line react-hooks/exhaustive-deps

  // While the assessment runs: ask again every 3 seconds, until it is done or failed
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => assessmentsApi.get(candidateId).then(setReport).catch((e) => setError(e.message)),
      LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [candidateId, running]);

  // On "Create assessment" / "Create again": → POST /api/candidates/{id}/assessment (answers at once, "running")
  async function start() {
    setError("");
    try { setReport(await assessmentsApi.start(candidateId)); } catch (e) { setError(e.message); }
  }

  if (!auth.get()) {
    return <div className="room-message"><p>Please open the report from the Reports page of LumenAI (you need to be logged in).</p></div>;
  }

  const status = report?.status;
  const weight = report?.cv_weight ?? 40;
  const updated = report?.updated_at ? new Date(report.updated_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";

  return (
    <div className="analysis-page report-page">
      <div className="analysis-bar">
        <div>
          <b>Assessment report · {report?.candidate_name || "candidate"}</b>
          <div className="muted small">{report?.job_title}{status === "done" && updated && ` · ${updated}`}</div>
        </div>
        <div className="no-print">
          <button type="button" onClick={start} disabled={!report || running}>
            {running ? "Assessing..." : status === "not_started" ? "Create assessment" : "Create again"}</button>
          <button type="button" className="secondary" onClick={() => window.print()} disabled={status !== "done"}>Export PDF</button>
          <button type="button" className="secondary" onClick={() => downloadHtml(report)} disabled={status !== "done"}>Download HTML</button>
          <button type="button" className="secondary" onClick={() => window.close()}>Close tab</button>
        </div>
      </div>

      <div className="analysis-body report-body">
        {error && <p className="error">{error}</p>}
        {status === "not_started" && <p className="muted">No assessment yet. Click "Create assessment".</p>}
        {running && <p className="analysis-running">Writing the assessment. This takes about a minute; the report appears here by itself.</p>}
        {status === "failed" && <p className="error">The assessment failed: {report.error}</p>}

        {report && report.overall_score !== null && (
          <>
            <div className="analysis-summary">
              <div className="summary-tile"><span className="muted small">CV score ({weight} %)</span>
                <b className={`summary-number ${tone(report.cv_score)}`}>{report.cv_score}</b></div>
              <div className="summary-tile"><span className="muted small">Interview score ({100 - weight} %)</span>
                <b className={`summary-number ${tone(report.interview_score)}`}>{report.interview_score}</b></div>
              <div className="summary-tile"><span className="muted small">Overall score</span>
                <b className={`summary-number ${tone(report.overall_score)}`}>{report.overall_score}</b></div>
            </div>

            <div className="card"><h3>Summary</h3><p>{report.summary}</p></div>
            <div className="report-grid">
              <div className="card"><h3>Strengths</h3>
                <EvidenceList items={report.strengths} empty="No strength could be proven with a quote." /></div>
              <div className="card"><h3>Weaknesses</h3>
                <EvidenceList items={report.weaknesses} empty="No weakness could be proven with a quote." /></div>
            </div>
            <div className="report-grid">
              <div className="card"><h3>Evidence gaps</h3>
                <p className="muted small">Job requirements with no proof in the CV or the interview.</p>
                {report.evidence_gaps.length ? report.evidence_gaps.map((gap) => <span key={gap} className="badge failed">{gap}</span>)
                  : <p className="small">None: every requirement has some proof.</p>}</div>
              <div className="card"><h3>Areas to explore</h3>
                <ul className="evidence-list">
                  {report.recommended_areas.map((a) => <li key={a.area}><b>{a.area}</b><div className="small muted">{a.why}</div></li>)}
                </ul></div>
            </div>
            <p className="small muted">Every strength and weakness has a quote that was checked against the CV or the
              interview transcript{report.repair_rounds ? ` (${report.repair_rounds} correction round${report.repair_rounds > 1 ? "s" : ""})` : ""}.
              Only the words were assessed, never voice or appearance.</p>
          </>
        )}

        {status === "done" && <DecisionCard key={report.updated_at} report={report} onSaved={setReport} />}
      </div>
    </div>
  );
}
