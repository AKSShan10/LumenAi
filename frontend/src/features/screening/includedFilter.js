// The filter of the Included list: the top K by final score, or everyone with a final score of at least X.
// The list is already sorted by final score (highest first), so both filters keep the start of the list and the
// rank (#) stays the candidate's real place among all included. Only saved scores are used: no AI call, so the
// same filter on the same scores always shows the same candidates.
// Returns { shown, message } or { shown: list, problem } when the typed value cannot be used.
export function filterIncluded(list, filter) {
  if (filter.mode === "all") return { shown: list, message: "" };
  const scored = list.filter((row) => row.weighted_score != null);       // no final score: hidden while filtering
  const text = String(filter.value).trim();
  const value = Number(text);

  if (filter.mode === "top") {
    if (text === "" || !Number.isInteger(value) || value < 1) {
      return { shown: list, problem: "Top K needs a whole number of 1 or more." };
    }
    if (value >= scored.length) {
      return { shown: scored, message: `Showing all ${scored.length} scored of ${list.length} included (asked for the top ${value}).` };
    }
    const cut = scored[value - 1].weighted_score;                         // the score of the K-th candidate
    const shown = scored.filter((row) => row.weighted_score >= cut);      // a tie at the cut-off is shown too
    const tie = shown.length > value ? `: ${shown.length} shown because of a tie at ${cut}` : "";
    return { shown, message: `Showing the top ${value} of ${list.length} included${tie}.` };
  }

  if (text === "" || Number.isNaN(value) || value < 0 || value > 100) {
    return { shown: list, problem: "The minimum score must be a number from 0 to 100." };
  }
  const shown = scored.filter((row) => row.weighted_score >= value);
  return { shown, message: `Showing ${shown.length} of ${list.length} included with a final score of ${value} or more.` };
}
