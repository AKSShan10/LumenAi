// Where the interviewer's login token is kept.
// sessionStorage = forgotten when the browser tab closes.
const KEY = "lumenai_token";
export const auth = {
  get() { try { return sessionStorage.getItem(KEY); } catch { return null; } },
  set(token) { try { sessionStorage.setItem(KEY, token); } catch { /* private mode: token stays only in memory */ } },
  clear() { try { sessionStorage.removeItem(KEY); } catch { /* ignore */ } },
};
