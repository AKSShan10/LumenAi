// Where the interviewer's login token is kept, with the name and email that are shown in the sidebar.
// sessionStorage = forgotten when the browser tab closes.
const KEY = "lumenai_token";
const EMAIL_KEY = "lumenai_email";
const NAME_KEY = "lumenai_name";
// Reads one value from sessionStorage; gives "" if it is missing or storage is blocked
const read = (key) => { try { return sessionStorage.getItem(key) || ""; } catch { return ""; } };

export const auth = {
  get() { return read(KEY) || null; },
  email() { return read(EMAIL_KEY); },
  name() { return read(NAME_KEY); },
  set(token, email = "", name = "") {
    try { sessionStorage.setItem(KEY, token); sessionStorage.setItem(EMAIL_KEY, email); sessionStorage.setItem(NAME_KEY, name); }
    catch { /* private mode: nothing is kept after a reload */ }
  },
  clear() {
    try { [KEY, EMAIL_KEY, NAME_KEY].forEach((key) => sessionStorage.removeItem(key)); } catch { /* ignore */ }
  },
};
