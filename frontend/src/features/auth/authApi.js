// Interviewer accounts: is there one, create the first one, log in, change the password, register more
import { del, json, request } from "../../shared/api/httpClient.js";

export const authApi = {
  status: () => request("/api/auth/status"),                                    // { has_account }
  // POST /api/auth/setup: creates the very first interviewer account and logs in
  setup: (fullName, email, password) => request("/api/auth/setup", json({ full_name: fullName, email, password })),
  // POST /api/auth/login: checks email and password and gets back the login token
  login: (email, password) => request("/api/auth/login", json({ email, password })),
  // POST /api/auth/change-password: changes the logged-in interviewer's password
  changePassword: (currentPassword, newPassword) =>
    request("/api/auth/change-password", json({ current_password: currentPassword, new_password: newPassword })),
  // GET /api/auth/users: the list of interviewer accounts
  users: () => request("/api/auth/users"),
  // POST /api/auth/users: registers one more interviewer account
  addUser: (fullName, email, password) => request("/api/auth/users", json({ full_name: fullName, email, password })),
  // DELETE /api/auth/users/{id}: removes an interviewer account
  removeUser: (id) => request(`/api/auth/users/${id}`, del),
};
