// App name, "Test AI connection" and the workflow run log
import { request } from "../../shared/api/httpClient.js";

export const systemApi = {
  // GET /api/health: tells that the backend is up and gives the app name
  health: () => request("/api/health"),
  // GET /api/llm-check: tests the connection to the AI model
  llmCheck: () => request("/api/llm-check"),
  driveCheck: () => request("/api/drive-check"),          // can the job's Google Form and the CVs be read?
  postingCheck: () => request("/api/posting-check"),      // is Blogger set up?
  // GET /api/email-check: checks that invitation emails can be sent
  emailCheck: () => request("/api/email-check"),
  sttCheck: () => request("/api/stt-check"),              // is speech-to-text (Deepgram) set up? (sends no sound)
  videoCheck: () => request("/api/video-check"),          // are the LiveKit keys there? (connects to nothing)
  // GET /api/workflow-runs?limit=15: the 15 latest workflow runs for the log
  workflowRuns: () => request("/api/workflow-runs?limit=15"),
};
