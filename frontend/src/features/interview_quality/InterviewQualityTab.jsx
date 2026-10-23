// The "Interview quality" tab of the analysis page (F10): the quality of the interview process itself, not of the
// candidate. Code measures the facts (speaking time, coverage, answer signal, consistency); the AI reviews the
// questions and suggests improvements, each based on one measured fact. The candidate never sees it, and it never
// changes a candidate's score or decision.
import { useEffect, useState } from "react";
import { interviewQualityApi } from "./interviewQualityApi.js";

const LOOK_AGAIN_MS = 3000;
const COVERAGE = {
  shown: ["Asked and shown", "done", "A question covered it and the answer showed it."],
  no_signal: ["Asked, little signal", "draft", "A question covered it, but the answer showed little about it."],
  not_asked: ["Not asked", "failed", "No question in this interview covered it."],
};
const BASIS = { requirement: "Competency", question: "Question", talk: "Speaking time", consistency: "Consistency" };

// The colour of a score: green 75 and above, amber 50 and above, red below 50
function tone(value) {
  if (value === null || value === undefined) return "";
  return value >= 75 ? "good" : value >= 50 ? "fair" : "weak";
}

// Seconds as m:ss (for the speaking time)
function minutes(seconds) {
  const s = Math.round(seconds || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function InterviewQualityTab({ sessionId, analysisDone, showInTranscript }) {
  const [quality, setQuality] = useState(null);
  const [error, setError] = useState("");
  const running = quality?.status === "running";

  // → GET /api/sessions/{id}/quality when the tab opens
  useEffect(() => {
    interviewQualityApi.get(sessionId).then(setQuality).catch((e) => setError(e.message));
  }, [sessionId]);

  // While it runs: ask again every 3 seconds, until it is done or failed
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => interviewQualityApi.get(sessionId).then(setQuality).catch((e) => setError(e.message)),
      LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [sessionId, running]);

  // On "Check interview quality": → POST /api/sessions/{id}/quality (answers at once with "running")
  async function start() {
    setError("");
    try { setQuality(await interviewQualityApi.start(sessionId)); } catch (e) { setError(e.message); }
  }

  const status = quality?.status;
  return (
    <div className="quality">
      <div className="card">
        <div className="row-between">
          <h3>Interview quality</h3>
          <button type="button" onClick={start} disabled={!quality || running || !analysisDone}>
            {running ? "Checking..." : status === "done" || status === "failed" ? "Check again" : "Check interview quality"}
          </button>
        </div>
        <p className="muted small">How well the interview itself went: the questions, the competencies covered, the
          speaking time and the consistency with the job's other interviews. It is for the interviewer only and does
          not change any score or decision.</p>
        {!analysisDone && <p className="muted small">Analyse the answers first. The interview quality uses the Q&A analysis.</p>}
        {error && <p className="error">{error}</p>}
        {running && <p className="analysis-running small">Checking the interview... this takes a few seconds.</p>}
        {status === "failed" && <p className="error">The check failed: {quality.error}</p>}
      </div>
      {status === "done" && <QualityResult quality={quality} showInTranscript={showInTranscript} />}
    </div>
  );
}

function QualityResult({ quality, showInTranscript }) {
  const talk = quality.talk || {};
  const share = talk.interviewer_share;
  return (
    <>
      <div className="analysis-summary">
        <div className="summary-tile"><span className="muted small">Interview quality</span>
          <b className={`summary-number ${tone(quality.quality_score)}`}>{quality.quality_score ?? "–"}</b></div>
        {quality.scores.map((s) => (
          <div key={s.key} className="summary-tile"><span className="muted small">{s.name}</span>
            <b className={`summary-number ${tone(s.score)}`}>{s.score ?? "–"}</b></div>
        ))}
      </div>
      <p className="muted small">Interview quality is the average of the scores above (a dash means it could not be
        measured, e.g. consistency needs two analysed interviews for the job).</p>

      <div className="card">
        <h3>Summary and improvements</h3>
        <p>{quality.summary}</p>
        <ol className="quality-recs">
          {quality.recommendations.map((r, i) => (
            <li key={i}><span className="badge">{BASIS[r.basis] || r.basis}{r.ref ? `: ${r.basis === "question" ? "Q" : ""}${r.ref}` : ""}</span>{" "}
              {r.text}
              {r.time !== null && r.time !== undefined && <> <button type="button" className="link"
                onClick={() => showInTranscript(r.time)}>Show in transcript</button></>}
            </li>
          ))}
        </ol>
        <p className="muted small">Every improvement is based on a fact measured by code; anything else was removed.</p>
      </div>

      <div className="quality-grid">
        <div className="card">
          <h3>Speaking time</h3>
          {share === null || share === undefined ? <p className="muted">No speech was transcribed.</p> : (
            <>
              <div className="quality-talk" title={`Interviewer ${share} % · Candidate ${Math.round((100 - share) * 10) / 10} %`}>
                <span className="quality-talk-interviewer" style={{ width: `${share}%` }}>Interviewer {share} %</span>
                <span className="quality-talk-candidate">Candidate {Math.round((100 - share) * 10) / 10} %</span>
              </div>
              <p className="small">Interviewer {minutes(talk.interviewer_sec)} · Candidate {minutes(talk.candidate_sec)} ·
                longest interviewer stretch {minutes(talk.longest_interviewer_sec)}</p>
              <p className={`small ${talk.balanced ? "muted" : "error"}`}>{talk.balanced
                ? "Balanced: the interviewer spoke 40 % of the time or less."
                : "Not balanced: the interviewer spoke more than 40 % of the time."}</p>
            </>
          )}
        </div>

        <div className="card">
          <h3>Competency coverage</h3>
          {quality.coverage.length ? (
            <table className="parts-table"><tbody>
              {quality.coverage.map((c) => (
                <tr key={c.requirement}>
                  <td>{c.requirement}{c.required ? " (required)" : ""}
                    {c.questions.length > 0 && <span className="muted small"> · Q{c.questions.join(", Q")}</span>}</td>
                  <td><span className={`badge ${COVERAGE[c.state][1]}`} title={COVERAGE[c.state][2]}>{COVERAGE[c.state][0]}</span></td>
                </tr>
              ))}
            </tbody></table>
          ) : <p className="muted">The job has no requirements.</p>}
        </div>
      </div>

      <div className="card">
        <h3>Questions</h3>
        <table>
          <thead><tr><th>#</th><th>Question</th><th>Relevance</th><th>Type</th><th>Signal</th><th>Suggestion</th></tr></thead>
          <tbody>
            {quality.questions.map((q) => (
              <tr key={q.n}>
                <td>{q.n}</td>
                <td>{q.question}<div className="muted small">{q.reason}</div></td>
                <td><span className={`mark ${tone(q.relevance)}`}>{q.relevance ?? "–"}</span></td>
                <td>{q.open ? "Open" : "Closed"}</td>
                <td>{q.signal === "low"
                  ? <span className="badge draft" title={q.signal_reason}>Little signal</span>
                  : <span className="badge done">Good</span>}
                  {q.signal === "low" && <div className="muted small">{q.signal_reason}</div>}
                  {q.time !== null && q.time !== undefined && <button type="button" className="link small"
                    onClick={() => showInTranscript(q.time)}>Show in transcript</button>}</td>
                <td className="small">{q.better || <span className="muted">–</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Consistency across this job's interviews</h3>
        {(quality.consistency.interviews || []).length < 2
          ? <p className="muted">Only one analysed interview for this job so far. Consistency is compared when there are two or more.</p>
          : (
            <>
              <table>
                <thead><tr><th>Candidate</th><th>Date</th><th>Questions</th><th>Minutes</th><th>Interviewer talk</th><th>Requirements asked</th></tr></thead>
                <tbody>
                  {quality.consistency.interviews.map((i) => (
                    <tr key={i.session_id} className={i.current ? "selected" : ""}>
                      <td>{i.candidate}{i.current ? " (this interview)" : ""}</td>
                      <td>{i.date ? new Date(i.date).toLocaleDateString() : "–"}</td>
                      <td>{i.questions}</td><td>{i.minutes}</td>
                      <td>{i.interviewer_share ?? "–"}{i.interviewer_share !== null && " %"}</td>
                      <td className="small">{i.asked.join(", ") || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small">{quality.consistency.uneven.length
                ? <>Asked in some interviews but not in others: <b>{quality.consistency.uneven.join(", ")}</b></>
                : "Every requirement was treated the same way in all interviews."}</p>
            </>
          )}
      </div>
      <p className="muted small">Only the words and the times were assessed, never voice, tone or appearance.</p>
    </>
  );
}
