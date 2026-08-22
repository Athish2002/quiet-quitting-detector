import { Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ApiKeyGate } from "./components/ApiKeyGate";
import { Console } from "./pages/Console";
import { DiagnosticRoom } from "./pages/DiagnosticRoom";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { Placeholder } from "./pages/Placeholder";

// S2 of the redesign: the four sibling pages become one shell with eight
// sections on real routes (design/REDESIGN_PLAN.md).
//
// The four existing pages are mounted at their new addresses unchanged. They
// still carry their old markup and will look like a mix of two designs until
// S3-S9 replace them one at a time -- that is the intended shape of the
// migration, and it keeps the app usable at every commit rather than dark for
// nine sessions.

function NotFound() {
  return (
    <section aria-labelledby="notfound-heading">
      <h1 id="notfound-heading">Page not found</h1>
      <p>
        That address does not exist. <a href="/">Back to the overview</a>.
      </p>
    </section>
  );
}

export function App() {
  return (
    <Router>
      <ApiKeyGate>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Home />} />
            <Route path="/cohort" element={<Console />} />
            <Route
              path="/person/:name"
              element={
                <Placeholder
                  eyebrow="Person detail"
                  title="One person, against their own earlier weeks."
                  intro="The score with its confidence, what drove it, the patterns that held for two weeks or more, and the conversation this suggests."
                  session="S5"
                />
              }
            />
            <Route path="/diagnostic" element={<DiagnosticRoom />} />
            <Route
              path="/ingest"
              element={
                <Placeholder
                  eyebrow="Ingest"
                  title="Bring a week of telemetry in."
                  intro="Every route in drops anything the allowlist does not name, before it is persisted. The receipt tells you exactly what was kept and what was refused."
                  session="S7"
                />
              }
            />
            <Route
              path="/simulator"
              element={
                <Placeholder
                  eyebrow="Simulator"
                  title="Try a shape of week and see what it scores."
                  intro="Nothing here is stored. It exists so you can see what the model reacts to before you trust it with someone real."
                  session="S8"
                />
              }
            />
            <Route path="/history" element={<History />} />
            <Route
              path="/audit"
              element={
                <Placeholder
                  eyebrow="Access trail & retention"
                  title="Who looked at whose assessment."
                  intro="Append-only and hash-chained. Refused requests are recorded too — a refusal is itself an audit record. Nothing on this page can edit or delete a row."
                  session="S11"
                />
              }
            />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ApiKeyGate>
    </Router>
  );
}
