// The line at the bottom of every page: who made the app, and the rule it follows.
export default function AppFooter({ appName = "LumenAI" }) {
  return (
    <footer className="app-footer no-print">
      <span>© {new Date().getFullYear()} {appName} · Recruitment and interview intelligence</span>
      <span>The AI suggests. People decide.</span>
    </footer>
  );
}
