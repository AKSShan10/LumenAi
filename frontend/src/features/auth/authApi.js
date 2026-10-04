// Login: passcode -> token
import { json, request } from "../../shared/api/httpClient.js";

export const authApi = {
  login: (passcode) => request("/api/auth/login", json({ passcode })),
};
