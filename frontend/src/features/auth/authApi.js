// Interviewer accounts: is there one, create the first one, log in, change the password, register more
import { del, json, request } from "../../shared/api/httpClient.js";

export const authApi = {
  status: () => request("/api/auth/status"),                                    // { has_account }
  setup: (fullName, email, password) => request("/api/auth/setup", json({ full_name: fullName, email, password })),
  login: (email, password) => request("/api/auth/login", json({ email, password })),
  changePassword: (currentPassword, newPassword) =>
    request("/api/auth/change-password", json({ current_password: currentPassword, new_password: newPassword })),
  users: () => request("/api/auth/users"),
  addUser: (fullName, email, password) => request("/api/auth/users", json({ full_name: fullName, email, password })),
  removeUser: (id) => request(`/api/auth/users/${id}`, del),
};
