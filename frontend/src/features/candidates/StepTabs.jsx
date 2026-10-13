import Icon from "../../shared/utils/Icon.jsx";

// The steps of the Candidates page, in hiring order. Each step has its own color (tone) and icon,
// so Included, Excluded and Shortlist never look the same.
export const STEPS = [
  { key: "applications", step: "Step 1", title: "Applications", icon: "people", tone: "slate" },
  { key: "included", step: "Step 2", title: "Included", icon: "check", tone: "green" },
  { key: "excluded", step: "Step 2", title: "Excluded", icon: "cross", tone: "red" },
  { key: "shortlist", step: "Step 3", title: "Shortlist", icon: "star", tone: "blue" },
];

// The tab bar at the top: one tab per step with its count; counts = {applications, included, ...}, extra = small notes
export function StepTabs({ active, counts, extra = {}, onPick }) {
  return (
    <nav className="step-tabs" role="tablist" aria-label="Candidate steps">
      {STEPS.map((s, index) => (
        <div key={s.key} className="step-slot">
          {index > 0 && s.step !== STEPS[index - 1].step && <span className="step-arrow" aria-hidden="true">›</span>}
          <button type="button" role="tab" aria-selected={active === s.key}
                  className={`step-tab tone-${s.tone} ${active === s.key ? "active" : ""}`} onClick={() => onPick(s.key)}>
            <span className="step-icon"><Icon name={s.icon} size={18} /></span>
            <span className="step-text">
              <small>{s.step}</small>
              <b>{s.title}</b>
              {extra[s.key] && <em>{extra[s.key]}</em>}
            </span>
            <span className="step-count">{counts[s.key] ?? 0}</span>
          </button>
        </div>
      ))}
    </nav>
  );
}

// The colored head of one section: icon, title, count, one line about it, and buttons on the right (children)
export function SectionHead({ step, count, text, children }) {
  const s = STEPS.find((x) => x.key === step);
  return (
    <div className="section-head">
      <span className="section-icon"><Icon name={s.icon} size={22} /></span>
      <div className="section-title">
        <h3>{s.title} <span className="section-count">{count}</span></h3>
        <p className="muted small">{text}</p>
      </div>
      {children && <div className="section-actions">{children}</div>}
    </div>
  );
}
