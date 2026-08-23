import { Route, BrowserRouter, HashRouter, Routes } from "react-router-dom";
import { isDemo } from "./api/client";
import { AppShell } from "./components/AppShell";
import { ApiKeyGate } from "./components/ApiKeyGate";
import { RoleProvider, useRole } from "./contexts/RoleContext";
import { Cohort } from "./pages/Cohort";
import { DiagnosticRoom } from "./pages/DiagnosticRoom";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { PersonDetail } from "./pages/PersonDetail";
import { Ingest } from "./pages/Ingest";
import { Simulator } from "./pages/Simulator";
import { AccessTrail } from "./pages/AccessTrail";
import { ManagerBriefings } from "./pages/ManagerBriefings";
import { EmployeePortal } from "./pages/EmployeePortal";

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

function HomeRoute() {
  const { role } = useRole();
  if (role === "employee") {
    return <EmployeePortal />;
  }
  if (role === "manager") {
    return <ManagerBriefings />;
  }
  return <Home />;
}

function ProtectedRoute({
  section,
  children,
}: {
  section: string;
  children: React.ReactNode;
}) {
  const { hasAccess } = useRole();
  if (!hasAccess(section)) {
    return (
      <section aria-labelledby="restricted-heading" className="page">
        <h1 id="restricted-heading">Access restricted</h1>
        <p>
          Your current role does not have permission to view this section.{" "}
          <a href="/">Back to overview</a>.
        </p>
      </section>
    );
  }
  return <>{children}</>;
}

export function App() {
  const Router = isDemo() ? HashRouter : BrowserRouter;
  return (
    <Router>
      <RoleProvider>
        <ApiKeyGate>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/" element={<HomeRoute />} />
              <Route
                path="/cohort"
                element={
                  <ProtectedRoute section="cohort">
                    <Cohort />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/person/:name"
                element={
                  <ProtectedRoute section="person">
                    <PersonDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/diagnostic"
                element={
                  <ProtectedRoute section="diagnostic">
                    <DiagnosticRoom />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/ingest"
                element={
                  <ProtectedRoute section="ingest">
                    <Ingest />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/simulator"
                element={
                  <ProtectedRoute section="simulator">
                    <Simulator />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/history"
                element={
                  <ProtectedRoute section="history">
                    <History />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/audit"
                element={
                  <ProtectedRoute section="audit">
                    <AccessTrail />
                  </ProtectedRoute>
                }
              />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ApiKeyGate>
      </RoleProvider>
    </Router>
  );
}
