// The candidate's page. It is opened with the private link from the invitation email (/join/<secret>),
// needs no login, and shows nothing from the interviewer's app.
// Placeholder: the interview feature replaces this with the real join page, which checks the link.
export default function CandidateJoinPage({ joinToken }) {
  return (
    <div className="login-page">
      <div className="card login">
        <h1>Interview</h1>
        <p className="muted">The interview page is not built yet.</p>
      </div>
    </div>
  );
}
