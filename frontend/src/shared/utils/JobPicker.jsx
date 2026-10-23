import { currentJob } from "./currentJob.js";

// The "Job" dropdown of every page: "All jobs" first, then the jobs. The choice is saved, so the other pages open
// on the same job. value: a job id or null (All jobs); onChange(id or null).
export default function JobPicker({ id, jobs, value, onChange, allLabel = "All jobs", showStatus = false }) {
  function pick(text) {
    const chosen = text ? Number(text) : null;
    currentJob.set(chosen);
    onChange(chosen);
  }
  return (
    <label htmlFor={id} className="inline">Job
      <select id={id} value={value ?? ""} onChange={(e) => pick(e.target.value)}>
        <option value="">{allLabel}</option>
        {jobs.map((j) => (
          <option key={j.id} value={j.id}>#{j.id} {j.title}{showStatus && j.status !== "approved" ? " (draft)" : ""}</option>
        ))}
      </select>
    </label>
  );
}
