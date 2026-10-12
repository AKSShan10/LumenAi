// App name, "Test AI connection" and the workflow run log
import { request } from "../../shared/api/httpClient.js";

export const systemApi = {
  health: () => request("/api/health"),
  llmCheck: () => request("/api/llm-check"),
  driveCheck: () => request("/api/drive-check"),          // can the job's Google Form and the CVs be read?
  postingCheck: () => request("/api/posting-check"),      // is Blogger set up?
  emailCheck: () => request("/api/email-check"),          // can invitations be sent? (SMTP, through the email MCP server)
  workflowRuns: () => request("/api/workflow-runs?limit=15"),
};
