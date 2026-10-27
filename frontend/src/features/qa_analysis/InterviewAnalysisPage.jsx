import { useEffect, useState } from "react";
import { auth } from "../../shared/api/authToken.js";
import { download } from "../../shared/api/httpClient.js";
import { interviewsApi } from "../interviews/interviewsApi.js";
import { transcriptsApi } from "../transcripts/transcriptsApi.js";
import { TurnList, clock } from "../transcripts/LiveTranscript.jsx";
import { qaAnalysisApi } from "./qaAnalysisApi.js";
import InterviewQualityTab from "../interview_quality/InterviewQualityTab.jsx";
import { navigate } from "../../shared/utils/navigate.js";

// The Q&A analysis of one interview, a page inside the app (/interview-analysis/<id>), opened from the Interviews
// page. The tab gets a copy of the login from the tab that opened it.
//   top:   who and when, "Analyse answers" / "Analyse again", the interview score and the requirements shown
//   tabs:  Marks           every question with its six marks; click a row to see the answer, reasons, quote and a
//                          suggested follow-up question for what the answer missed
//          By requirement  each job requirement: which questions tested it, the best score, shown or not
//          Transcript      everything said; "Show in transcript" jumps to the line of a quote
//          Interview quality  the quality of the interview process itself (F10, InterviewQualityTab.jsx)
// The AI suggests the marks from the transcript text only. A person decides.
const LOOK_AGAIN_MS = 3000;            // while the analysis runs, the page asks again every 3 seconds
const GRADES = [["relevance", "Relevance"], ["accuracy", "Accuracy"], ["completeness", "Completeness"],
  ["articulation", "Articulation"], ["problem_solving", "Problem solving"], ["depth", "Depth"]];

// The interview scorecard (F9): six dimensions, each with its score bar, the reason and the best quote the candidate
// really said (a click shows that line in the transcript). The interview score is the average of the six.
function Scorecard({ card, score, showInTranscript }) {
  if (!card.length) {
    return <p className="muted small">This interview was analysed before the scorecard existed. Click "Analyse again" to
      see the six dimensions.</p>;
  }
  return (
    <div className="card scorecard">
      <div className="row-between">
        <h3>Interview scorecard</h3>
        <span className="small muted">Interview score <b className={`mark ${tone(score)}`}>{score ?? "–"}</b>
          {" "}= the average of the six dimensions, separate from the CV score</span>
      </div>
      {card.map((d) => (
        <div key={d.key} className="scorecard-row">
          <div className="dash-bar" title={`${d.name}: ${d.score ?? "–"}`}>
            <span className="dash-bar-label">{d.name}</span>
            <span className="dash-bar-track"><span className={`dash-bar-fill ${tone(d.score)}`}
                                                   style={{ width: `${d.score ?? 0}%` }} /></span>
            <span className="dash-bar-value"><b>{d.score ?? "–"}</b></span>
          </div>
          <div className="small muted scorecard-why">{d.reason}
            {d.quote && <> · "{d.quote}" {d.time !== null && d.time !== undefined && (
              <button type="button" className="link" onClick={() => showInTranscript(d.time)}>Show in transcript</button>)}</>}
          </div>
        </div>
      ))}
      <p className="small muted">Alignment is counted by code from the job requirements the answers showed. The other
        dimensions are the averages of the AI's grades, checked by code. Only the words were assessed, never voice or
        appearance.</p>
    </div>
  );
}

// The colour of a mark: green 75 and above, amber 50 and above, red below 50
function tone(value) {
  if (value === null || value === undefined) return "";
  return value >= 75 ? "good" : value >= 50 ? "fair" : "weak";
}

// One mark in a coloured box ("–" when there is none)
const Mark = ({ value }) => <span className={`mark ${tone(value)}`}>{value ?? "–"}</span>;

// The "Marks" tab: the table on the left, the chosen question on the right
function MarksTab({ items, chosen, setChosen, showInTranscript }) {
  const [lowestFirst, setLowestFirst] = useState(false);
  const [smallTalk, setSmallTalk] = useState(false);
  let rows = items.filter((i) => smallTalk || i.job_related);
  if (lowestFirst) rows = [...rows].sort((a, b) => (a.score ?? 101) - (b.score ?? 101));
  const item = items.find((i) => i.position === chosen);

  return (
    <div className="analysis-grid">
      <div className="card">
        <div className="row-between">
          <h3>Marks</h3>
          <div className="small">
            <label className="inline"><input type="checkbox" checked={lowestFirst}
              onChange={(e) => setLowestFirst(e.target.checked)} /> Lowest score first</label>{" "}
            <label className="inline"><input type="checkbox" checked={smallTalk}
              onChange={(e) => setSmallTalk(e.target.checked)} /> Show small talk</label>
          </div>
        </div>
        <div className="table-scroll">
          <table className="marks-table">
            <thead>
              <tr><th>#</th><th>Question</th>{GRADES.map(([key, label]) => <th key={key}>{label}</th>)}<th>Score</th></tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i.position} className={i.position === chosen ? "chosen" : ""} onClick={() => setChosen(i.position)}>
                  <td>{i.position}</td>
                  <td className="marks-question">{i.question}{!i.job_related && <span className="muted"> (small talk)</span>}</td>
                  {GRADES.map(([key]) => <td key={key}><Mark value={i[key]} /></td>)}
                  <td><b><Mark value={i.score} /></b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="muted">No graded answers.</p>}
        <p className="muted small">Click a row to see the answer, the reason for each mark and the quote.</p>
      </div>

      <div className="card analysis-detail">
        {!item ? <p className="muted">Click a question in the table.</p> : (
          <>
            <h3>{item.position}. {item.question}</h3>
            <p className="small">
              {item.split_from_multi_part && <span className="badge">Part of a longer question</span>}
              {!item.job_related && <span className="badge">Small talk · not graded</span>}
              {item.requirements.map((r) => <span key={r} className="badge">{r}</span>)}
            </p>
            <div className="qa-answer small">{item.answer}</div>
            {item.job_related && (
              <>
                <ul className="detail-grades">
                  {GRADES.map(([key, label]) => (
                    <li key={key}><Mark value={item[key]} /> <b>{label}</b>
                      <div className="small">{item.reasons[key] || "No reason given."}</div></li>
                  ))}
                </ul>
                <p><b>Answer score: <Mark value={item.score} /></b> <span className="muted small">(average of the six grades)</span></p>
                {item.follow_up && (
                  <p className="follow-up small"><b>Suggested follow-up:</b> {item.follow_up}{" "}
                    <button type="button" className="link" onClick={() => navigator.clipboard?.writeText(item.follow_up)}>Copy</button></p>
                )}
                {item.evidence_quote ? (
                  <p className="small qa-quote">"{item.evidence_quote}" <span className="muted">at {clock(item.evidence_time)}</span>{" "}
                    <button type="button" className="link" onClick={() => showInTranscript(item.evidence_time)}>Show in transcript</button></p>
                ) : <p className="small muted">No quote could be checked in the transcript.</p>}
                <p className="small muted">{item.references.length ? `Accuracy based on company document: ${item.references.join(", ")}`
                  : "No company document was used for accuracy."}</p>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// The "By requirement" tab: one row per job requirement
function RequirementsTab({ analysis, openQuestion }) {
  const rows = [...analysis.covered, ...analysis.uncovered].map((name) => {
    const tested = analysis.items.filter((i) => i.job_related && i.requirements.includes(name));
    const scores = tested.map((i) => i.score).filter((s) => s !== null);
    const state = analysis.covered.includes(name) ? "Shown" : tested.length ? "Not shown" : "Not asked";
    return { name, tested, best: scores.length ? Math.max(...scores) : null, state };
  });
  return (
    <div className="card">
      <h3>By requirement</h3>
      <p className="muted small">A requirement is shown when an answer about it scored 50 or more. "Not asked" means no
        question was about it.</p>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Requirement</th><th>Questions</th><th>Best score</th><th>Result</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <td><b>{r.name}</b></td>
                <td>{r.tested.length ? r.tested.map((i) => (
                  <button key={i.position} type="button" className="link req-question" onClick={() => openQuestion(i.position)}>
                    Q{i.position}</button>)) : <span className="muted">–</span>}</td>
                <td><Mark value={r.best} /></td>
                <td><span className={`badge ${r.state === "Shown" ? "done" : r.state === "Not shown" ? "failed" : ""}`}>{r.state}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function InterviewAnalysisPage({ sessionId }) {
  const query = new URLSearchParams(window.location.search);
  const first = query.get("tab");
  const time = query.get("t");                      // from the assessment report: the transcript line to show
  const [tab, setTab] = useState(["transcript", "quality"].includes(first) ? first : "marks");  // marks | requirements | transcript | quality
  const [interview, setInterview] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [turns, setTurns] = useState([]);
  const [chosen, setChosen] = useState(null);       // the question shown on the right of the Marks tab
  const [marked, setMarked] = useState(time === null ? null : Number(time));   // the time "Show in transcript" jumps to
  const [error, setError] = useState("");
  const running = analysis?.status === "running";

  // When the tab opens: the interview, the analysis and the transcript
  useEffect(() => {
    if (!auth.get()) return;
    // → GET /api/sessions/{id}: who and when
    interviewsApi.get(sessionId).then((row) => {
      setInterview(row);
      document.title = `Analysis: ${row.candidate_name || "candidate"}`;
    }).catch((e) => setError(e.message));
    // → GET /api/sessions/{id}/analysis and GET /api/sessions/{id}/transcript
    qaAnalysisApi.get(sessionId).then(setAnalysis).catch((e) => setError(e.message));
    transcriptsApi.transcript(sessionId).then(setTurns).catch((e) => setError(e.message));
  }, [sessionId]);

  // While the analysis runs: ask again every 3 seconds, until it is done or failed
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => qaAnalysisApi.get(sessionId).then(setAnalysis).catch((e) => setError(e.message)),
      LOOK_AGAIN_MS);
    return () => clearInterval(timer);
  }, [sessionId, running]);

  // The first graded question is shown on the right when the result arrives
  useEffect(() => {
    if (analysis?.status === "done" && !analysis.items.some((i) => i.position === chosen)) {
      setChosen((analysis.items.find((i) => i.job_related) || analysis.items[0])?.position ?? null);
    }
  }, [analysis]);                                    // eslint-disable-line react-hooks/exhaustive-deps

  // "Show in transcript": the Transcript tab, scrolled to the marked line
  useEffect(() => {
    if (tab === "transcript" && marked !== null) {
      document.querySelector(".transcript-turn.marked")?.scrollIntoView({ block: "center" });
    }
  }, [tab, marked]);

  // On "Analyse answers" / "Analyse again": → POST /api/sessions/{id}/analysis (answers at once with "running")
  async function start() {
    setError("");
    try { setAnalysis(await qaAnalysisApi.start(sessionId)); setTab("marks"); } catch (e) { setError(e.message); }
  }

  // "Next: assessment report": ?start=1 creates the report when there is none yet (Reports does the same)
  function openReport() {
    navigate(`/assessment-report/${interview.candidate_id}?start=1`);
  }

  // → GET /api/sessions/{id}/transcript.txt: the transcript as a text file
  function saveTranscript() {
    download(`/api/sessions/${sessionId}/transcript.txt`, `interview-${sessionId}-transcript.txt`).catch((e) => setError(e.message));
  }

  if (!auth.get()) {
    return <div className="room-message"><p>Please open the analysis from the Interviews page of LumenAI (you need to be logged in).</p></div>;
  }

  const status = analysis?.status;
  const graded = analysis?.items.filter((i) => i.score !== null).length ?? 0;
  const requirements = analysis ? analysis.covered.length + analysis.uncovered.length : 0;
  const when = interview?.started_at ? new Date(interview.started_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";

  return (
    <div className="analysis-page">
      <div className="analysis-bar">
        <div>
          <b>{interview?.candidate_name || "Candidate"}</b>
          <div className="muted small">{interview?.job_title}{when && ` · interview on ${when}`}</div>
        </div>
        <div>
          <button type="button" onClick={start} disabled={!analysis || running || interview?.status !== "ended"}>
            {running ? "Analysing..." : status === "done" || status === "failed" ? "Analyse again" : "Analyse answers"}</button>
          {status === "done" && interview && (        // the next step of the process: the report (Reports page)
            <button type="button" className="secondary" onClick={openReport}
                    title="The assessment report combines this analysis with the CV screening; the decision is recorded there.">
              Next: assessment report →</button>
          )}
        </div>
      </div>

      <div className="analysis-body">
        {error && <p className="error">{error}</p>}
        {interview && interview.status !== "ended" && <p className="muted">The answers can be analysed after the interview has ended.</p>}
        {status === "not_started" && interview?.status === "ended" && <p className="muted">Not analysed yet. Click "Analyse answers".</p>}
        {running && <p className="analysis-running">Analysing the answers. This takes about a minute; the marks appear here by themselves.</p>}
        {status === "failed" && <p className="error">The analysis failed: {analysis.error}</p>}

        {status === "done" && (
          <div className="analysis-summary">
            <div className="summary-tile"><span className="muted small">Interview score</span>
              <b className={`summary-number ${tone(analysis.interview_score)}`}>{analysis.interview_score ?? "–"}</b></div>
            <div className="summary-tile"><span className="muted small">Answers graded</span>
              <b className="summary-number">{graded} of {analysis.items.length}</b></div>
            <div className="summary-tile"><span className="muted small">Requirements shown</span>
              <b className="summary-number">{analysis.covered.length} of {requirements}</b></div>
            <div className="summary-tags small">
              <div>Shown: {analysis.covered.length ? analysis.covered.map((r) => <span key={r} className="badge done">{r}</span>)
                : <span className="muted">none</span>}</div>
              <div>Not shown: {analysis.uncovered.length ? analysis.uncovered.map((r) => <span key={r} className="badge failed">{r}</span>)
                : <span className="muted">none</span>}</div>
            </div>
          </div>
        )}

        {status === "done" && <Scorecard card={analysis.scorecard || []} score={analysis.interview_score}
                                         showInTranscript={(time) => { setMarked(time); setTab("transcript"); }} />}

        <div className="tabs">
          <button type="button" className={tab === "marks" ? "active" : ""} onClick={() => setTab("marks")}>Marks</button>
          <button type="button" className={tab === "requirements" ? "active" : ""} onClick={() => setTab("requirements")}>By requirement</button>
          <button type="button" className={tab === "transcript" ? "active" : ""} onClick={() => setTab("transcript")}>Transcript</button>
          <button type="button" className={tab === "quality" ? "active" : ""} onClick={() => setTab("quality")}>Interview quality</button>
        </div>

        {tab === "marks" && (status === "done"
          ? <MarksTab items={analysis.items} chosen={chosen} setChosen={setChosen}
              showInTranscript={(time) => { setMarked(time); setTab("transcript"); }} />
          : <p className="muted">The marks appear here after the analysis.</p>)}
        {tab === "requirements" && (status === "done"
          ? <RequirementsTab analysis={analysis} openQuestion={(n) => { setChosen(n); setTab("marks"); }} />
          : <p className="muted">The requirements appear here after the analysis.</p>)}
        {tab === "quality" && <InterviewQualityTab sessionId={sessionId} analysisDone={status === "done"}
                                                    showInTranscript={(time) => { setMarked(time); setTab("transcript"); }} />}
        {tab === "transcript" && (
          <div className="card">
            <div className="row-between">
              <h3>Transcript</h3>
              <button type="button" className="secondary" onClick={saveTranscript}>Download .txt</button>
            </div>
            <p className="muted small">Times are from the start of the interview. The speaker comes from each person's own microphone.</p>
            {turns.length ? <TurnList turns={turns} names={{ candidate: interview?.candidate_name }} marked={marked} />
              : <p className="muted">Nothing was transcribed in this interview.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
