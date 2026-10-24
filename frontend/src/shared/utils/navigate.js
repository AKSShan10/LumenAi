// Moves to another page of the app in the SAME tab, without reloading: writes the new address (history.pushState)
// and tells App to read it again (the same "popstate" event the browser's Back/Forward buttons send).
// So the browser's Back button returns to the page before, and refresh and bookmarks open the same page.
//   navigate("/interview-analysis/38?tab=transcript")
export function navigate(path) {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
