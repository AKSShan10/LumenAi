// App name, "Test AI connection" and the workflow run log
import { request } from "../../shared/api/httpClient.js";

export const systemApi = {
  health: () => request("/api/health"),
  llmCheck: () => request("/api/llm-check"),
  driveCheck: () => request("/api/drive-check"),          // can the response sheet and the CVs be read?
  postingCheck: () => request("/api/posting-check"),      // is Blogger set up?
  workflowRuns: () => request("/api/workflow-runs?limit=15"),
};
