import { NavLink, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { ApiKeyGate } from "./components/ApiKeyGate";
import { Console } from "./pages/Console";
import { DiagnosticRoom } from "./pages/DiagnosticRoom";
import { History } from "./pages/History";
import { Home } from "./pages/Home";

// All four pages migrated (§9's order: Diagnostic Room, Console, History, Home).
// The old static/index.html is retired -- see PROGRESS.md.
const NAV = [
  { to: "/", label: "Home" },
  { to: "/diagnostic", label: "Diagnostic room" },
  { to: "/console", label: "Console" },
  { to: "/history", label: "History" },
] as const;

function NotFound() {
  return (
    <main className="page">
      <h1>Page not found</h1>
      <p>
        That address does not exist. <a href="/">Back to the start</a>.
      </p>
    </main>
  );
}

export function App() {
  return (
    <Router>
      <ApiKeyGate>
        {/* Skip link first in the DOM: keyboard users should not have to tab
            through the whole nav on every page. */}
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        <header>
          <nav aria-label="Main">
            <ul>
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} end={item.to === "/"}>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </header>
        <div id="main-content">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/diagnostic" element={<DiagnosticRoom />} />
            <Route path="/console" element={<Console />} />
            <Route path="/history" element={<History />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </ApiKeyGate>
    </Router>
  );
}
