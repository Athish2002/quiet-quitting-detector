import { NavLink, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { ApiKeyGate } from "./components/ApiKeyGate";
import { DiagnosticRoom } from "./pages/DiagnosticRoom";

// Only the Diagnostic Room has been migrated so far. §9 prescribes exactly this
// order and pace -- "migrate page by page, one page per session", running
// alongside the old static/index.html until parity is proven. The remaining
// routes are placeholders rather than half-built pages, so nothing here claims
// to work that does not.
function NotMigrated({ page }: { page: string }) {
  return (
    <main className="page">
      <h1>{page}</h1>
      <p>
        This page has not been migrated to the new interface yet. It is still
        available in the original dashboard.
      </p>
    </main>
  );
}

export function App() {
  return (
    <Router>
      <ApiKeyGate>
        <nav aria-label="Main">
          <ul>
            <li><NavLink to="/">Diagnostic room</NavLink></li>
            <li><NavLink to="/console">Console</NavLink></li>
            <li><NavLink to="/history">History</NavLink></li>
          </ul>
        </nav>
        <Routes>
          <Route path="/" element={<DiagnosticRoom />} />
          <Route path="/console" element={<NotMigrated page="Console" />} />
          <Route path="/history" element={<NotMigrated page="History" />} />
        </Routes>
      </ApiKeyGate>
    </Router>
  );
}
