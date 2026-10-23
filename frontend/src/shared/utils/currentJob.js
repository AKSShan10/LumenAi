// The job chosen on one page is opened on every page (Candidates, Interviews, Reports, Talent Pool, Dashboard,
// Job Requirements). Kept in this browser tab (sessionStorage): a refresh keeps it, logging out clears it.
// null = "All jobs". The browser may block storage, so every read and write is in try/catch.
const KEY = "lumenai_job";

export const currentJob = {
  // The saved job if it is still in this page's list, otherwise null (All jobs)
  get(jobs = []) {
    try {
      const id = Number(sessionStorage.getItem(KEY));
      return jobs.some((j) => j.id === id) ? id : null;
    } catch { return null; }
  },
  // Saves the choice (null = All jobs)
  set(id) {
    try { if (id) sessionStorage.setItem(KEY, String(id)); else sessionStorage.removeItem(KEY); } catch { /* not kept */ }
  },
  clear() { this.set(null); },
};
