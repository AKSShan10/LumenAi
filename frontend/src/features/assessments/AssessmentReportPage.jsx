import { useEffect, useState } from "react";
import { auth } from "../../shared/api/authToken.js";
import { assessmentsApi } from "./assessmentsApi.js";
import { clock } from "../transcripts/LiveTranscript.jsx";
import TalentPoolCard from "../talent_pool/TalentPoolCard.jsx";
import { claimsApi } from "../claims/claimsApi.js";

// The assessment report of one candidate, in its own browser tab (/assessment-report/<candidate id>), opened from
// the Reports page. The tab gets a copy of the login from the tab that opened it.
//   scores (CV, interview, overall) and the parts behind them · summary · strengths and weaknesses with their proof
//   (CV, or the interview with the time: a link to that line of the transcript) · requirements (CV and interview) ·
//   evidence gaps · areas to explore with their requirement or quote · the interviewer's decision · Export PDF (the browser's print: only the report is printed)
//   · Download HTML (the same report as one HTML file that opens in any browser)
// ?start=1 (from "Create assessment"): the tab starts the assessment itself and shows the progress.
// The AI writes the report; the decision is always made by the interviewer.
const LOOK_AGAIN_MS = 3000;            // while the assessment runs, the page asks again every 3 seconds
const DECISIONS = [["hire", "Hire"], ["hold", "Hold"], ["reject", "Reject"]];

// The colour of a score: green 75 and above, amber 50 and above, red below 50
const tone = (value) => (value === null || value === undefined ? "" : value >= 75 ? "good" : value >= 50 ? "fair" : "weak");

// Makes text safe to put inside HTML ("<" and "&" in a CV would otherwise break the file)
const safe = (text) => String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// Where a quote comes from, as text: "CV" or "Interview · 01:05"
const where = (item) => (item.source === "Interview" && item.time !== null && item.time !== undefined
  ? `Interview · ${clock(item.time)}` : item.source);

// CV result and interview result of a requirement, in words
const CV_WORDS = { met: "Met", partial: "Partly", unmet: "Not met", unchecked: "Not checked" };
const shown = (value) => (value === true ? "Shown" : value === false ? "Not shown" : "–");

// The report as one self-contained HTML file (styles inside), for "Download HTML": opens in any browser, offline
function reportHtml(report) {
  const weight = report.cv_weight;
  const list = (items) => (items.length
    ? `<ul>${items.map((i) => `<li>${safe(i.text)}<div class="quote">"${safe(i.quote)}" · ${safe(where(i))}</div></li>`).join("")}</ul>`
    : "<p class=\"muted\">None proven with a quote.</p>");
  const parts = (rows) => rows.map((p) => `<tr><td>${safe(p.name)}</td><td>${p.score ?? "–"}</td></tr>`).join("");
  const areaBasis = (a) => [a.requirement && `Requirement: ${safe(a.requirement)}`,
    a.quote && `"${safe(a.quote)}" · ${safe(where(a))}`].filter(Boolean).join(" · ");
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
  li { margin-bottom: 8px; } table { border-collapse: collapse; width: 100%; font-size: 14px; }
  td, th { text-align: left; padding: 4px 8px; border-bottom: 1px solid #e3e7ef; } .parts { display: flex; gap: 24px; }
</style></head><body>
<h1>Assessment report · ${safe(report.candidate_name)}</h1>
<p class="muted">${safe(report.job_title)} · ${safe(new Date(report.updated_at).toLocaleString())}</p>
<div class="scores">
  <div class="score">CV score (${weight} %)<b>${report.cv_score}</b></div>
  <div class="score">Interview score (${100 - weight} %)<b>${report.interview_score}</b></div>
  <div class="score">Overall score<b>${report.overall_score}</b></div>
</div>
<div class="parts">
  <div><h2>CV score parts</h2><table>${parts(report.cv_parts)}</table></div>
  <div><h2>Interview score parts</h2><table>${parts(report.interview_parts)}</table></div>
</div>
<h2>Summary</h2><p>${safe(report.summary)}</p>
<h2>Strengths</h2>${list(report.strengths)}
<h2>Weaknesses</h2>${list(report.weaknesses)}
<h2>Requirements</h2><table><tr><th>Requirement</th><th>CV</th><th>Interview</th></tr>${report.requirements.map((r) =>
    `<tr><td>${safe(r.requirement)}${r.kind === "must" ? " (must)" : ""}</td><td>${CV_WORDS[r.cv] || safe(r.cv)}</td><td>${shown(r.interview)}</td></tr>`).join("")}</table>
<h2>Evidence gaps</h2>${report.evidence_gaps.length ? report.evidence_gaps.map((g) => `<span class="gap">${safe(g)}</span>`).join("")
    : "<p>None: every requirement has some proof.</p>"}
<h2>Areas to explore</h2><ul>${report.recommended_areas.map((a) => `<li><b>${safe(a.area)}</b><div class="quote">${safe(a.why)}</div>
<div class="quote">${areaBasis(a)}</div></li>`).join("")}</ul>
<h2>Decision</h2><p><b>${decision}</b></p>
<p class="muted">Every strength and weakness has a quote checked against the CV or the interview transcript (with the time
it was said); every area to explore is linked to a job requirement or a checked quote. The summary is written only from
these checked items. The AI wrote the report; the decision was made by the interviewer.</p>
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

// Where a quote comes from: "CV", or "Interview · 01:05" as a link to that line of the transcript (analysis page,
// new tab). Printed as plain text.
function Source({ item, sessionId }) {
  if (item.source !== "Interview" || item.time === null || item.time === undefined || !sessionId) return item.source;
  // → opens /interview-analysis/<id>?tab=transcript&t=<seconds>; window.open (inside the click) copies the login
  const open = () => window.open(`/interview-analysis/${sessionId}?tab=transcript&t=${item.time}`, "_blank");
  return (
    <>
      <button type="button" className="link no-print" onClick={open} title="Show in transcript">{where(item)}</button>
      <span className="print-inline">{where(item)}</span>
    </>
  );
}

// Strengths or weaknesses: the sentence, then the proof (the quote and where it is from)
function EvidenceList({ items, empty, sessionId }) {
  if (!items.length) return <p className="muted small">{empty}</p>;
  return (
    <ul className="evidence-list">
      {items.map((item, n) => (
        <li key={n}>{item.text}
          <div className="small muted">"{item.quote}" · <Source item={item} sessionId={sessionId} /></div></li>
      ))}
    </ul>
  );
}

// The parts behind a total, e.g. Skills 80, Experience 70 (from the CV screening or the Q&A analysis)
function Parts({ title, parts }) {
  return (
    <div className="card"><h3>{title}</h3>
      {parts.length ? (
        <table className="parts-table"><tbody>
          {parts.map((p) => <tr key={p.name}><td>{p.name}</td>
            <td><b className={tone(p.score)}>{p.score ?? "–"}</b></td></tr>)}
        </tbody></table>
      ) : <p className="muted small">Not available.</p>}
    </div>
  );
}

// CV claims compared with the interview (F8): each claim is supported, contradicted, unverified or not discussed.
// Prompts for the interviewer's follow-up questions; they never change a score or a decision.
const CLAIM = {
  contradicted: ["Possible contradiction", "draft", "The candidate's words in the interview do not seem to fit the CV."],
  unverified: ["Unverified claim", "shortlisted", "The topic came up, but the answer did not back the claim up."],
  not_discussed: ["Not discussed", "", "The claim never came up in the interview."],
  supported: ["Supported", "done", "The interview backs the claim up."],
};

function ClaimsCard({ candidateId, sessionId }) {
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");
  const running = check?.status === "running";

  // → GET /api/candidates/{id}/claims (again every 3 seconds while it runs)
  useEffect(() => { claimsApi.get(candidateId).then(setCheck).catch((e) => setError(e.message)); }, [candidateId]);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => claimsApi.get(candidateId).then(setCheck).catch((e) => setError(e.message)), LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [candidateId, running]);

  // "Check CV claims" / "Check again": → POST /api/candidates/{id}/claims
  async function start() {
    setError("");
    try { setCheck(await claimsApi.start(candidateId)); } catch (e) { setError(e.message); }
  }

  if (!check) return null;
  const counts = Object.fromEntries(Object.keys(CLAIM).map((s) => [s, check.claims.filter((c) => c.status === s).length]));
  return (
    <div className="card">
      <div className="row-between">
        <h3>Claims to follow up</h3>
        <button type="button" className="secondary no-print" onClick={start} disabled={running}>
          {running ? "Checking..." : check.status === "not_started" ? "Check CV claims" : "Check again"}</button>
      </div>
      <p className="muted small">The CV's concrete claims are compared with what the candidate said in the interview.
        These are prompts for your follow-up questions, not accusations; they do not change any score or decision.</p>
      {error && <p className="error small">{error}</p>}
      {check.status === "not_started" && <p className="muted small">Not checked yet.</p>}
      {running && <p className="analysis-running">Comparing the CV with the interview. The result appears here by itself.</p>}
      {check.status === "failed" && <p className="error small">The check failed: {check.error}</p>}
      {check.status === "done" && check.claims.length === 0 && <p className="muted small">No concrete claims were found in the CV.</p>}
      {check.claims.length > 0 && (
        <>
          <div className="claim-counts">
            {Object.entries(CLAIM).map(([key, [label, badge]]) => (
              <span key={key} className={`badge ${badge}`} title={CLAIM[key][2]}>{label} {counts[key]}</span>))}
          </div>
          <ul className="claim-list">
            {check.claims.map((c, n) => (
              <li key={n} className={`claim ${c.status}`}>
                <div><span className={`badge ${CLAIM[c.status][1]}`}>{CLAIM[c.status][0]}</span> <b>{c.claim}</b></div>
                <div className="small muted">CV: "{c.cv_quote}"</div>
                {c.interview_quote && (
                  <div className="small muted">Said: "{c.interview_quote}" · <Source item={{ source: "Interview", time: c.time }} sessionId={sessionId} /></div>
                )}
                <div className="small">{c.note}</div>
                {c.follow_up && <div className="small claim-question">Ask: {c.follow_up}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
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

            <div className="report-grid">
              <Parts title={`CV score parts (${report.cv_score})`} parts={report.cv_parts} />
              <Parts title={`Interview score parts (${report.interview_score})`} parts={report.interview_parts} />
            </div>

            <div className="card"><h3>Summary</h3><p>{report.summary}</p>
              <p className="small muted">Written only from the checked strengths, weaknesses and evidence gaps below.</p></div>
            <div className="report-grid">
              <div className="card"><h3>Strengths</h3>
                <EvidenceList items={report.strengths} sessionId={report.session_id}
                              empty="No strength could be proven with a quote." /></div>
              <div className="card"><h3>Weaknesses</h3>
                <EvidenceList items={report.weaknesses} sessionId={report.session_id}
                              empty="No weakness could be proven with a quote." /></div>
            </div>
            {report.requirements.length > 0 && (
              <div className="card"><h3>Requirements</h3>
                <p className="muted small">What the CV screening found for each requirement, and whether an interview
                  answer showed it.</p>
                <div className="table-scroll"><table>
                  <thead><tr><th>Requirement</th><th>CV</th><th>Interview</th></tr></thead>
                  <tbody>
                    {report.requirements.map((r) => (
                      <tr key={r.requirement}>
                        <td>{r.requirement}{r.kind === "must" && <span className="muted small"> (must)</span>}</td>
                        <td><span className={`badge ${r.cv === "met" ? "done" : r.cv === "unmet" ? "failed" : ""}`}
                                  title={r.cv_how}>{CV_WORDS[r.cv] || r.cv}</span></td>
                        <td>{r.interview === null ? "–"
                          : <span className={`badge ${r.interview ? "done" : ""}`}>{shown(r.interview)}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              </div>
            )}
            <div className="report-grid">
              <div className="card"><h3>Evidence gaps</h3>
                <p className="muted small">Job requirements with no proof in the CV or the interview.</p>
                {report.evidence_gaps.length ? report.evidence_gaps.map((gap) => <span key={gap} className="badge failed">{gap}</span>)
                  : <p className="small">None: every requirement has some proof.</p>}</div>
              <div className="card"><h3>Areas to explore</h3>
                <ul className="evidence-list">
                  {report.recommended_areas.map((a) => (
                    <li key={a.area}><b>{a.area}</b><div className="small muted">{a.why}</div>
                      <div className="small muted">
                        {a.requirement && <span className="badge">{a.requirement}</span>}
                        {a.quote && <>"{a.quote}" · <Source item={a} sessionId={report.session_id} /></>}
                      </div></li>
                  ))}
                </ul></div>
            </div>
            <p className="small muted">Every strength and weakness has a quote that was checked against the CV or the
              interview transcript{report.repair_rounds ? ` (${report.repair_rounds} correction round${report.repair_rounds > 1 ? "s" : ""})` : ""};
              an interview time opens that line of the transcript. Every area to explore is linked to a job requirement
              or a checked quote. Only the words were assessed, never voice or appearance.</p>
          </>
        )}

        {status === "done" && <ClaimsCard candidateId={report.candidate_id} sessionId={report.session_id} />}
        {status === "done" && <DecisionCard key={report.updated_at} report={report} onSaved={setReport} />}
        {status === "done" && <TalentPoolCard candidateId={report.candidate_id} />}
      </div>
    </div>
  );
}
