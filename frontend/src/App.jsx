import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { RequireRole, homeFor, useAuth } from "./auth.jsx";
import { Login, Register } from "./pages/Login.jsx";
import { ApplicationDetail, ApplyForm, MyApplications } from "./pages/applicant/Applicant.jsx";
import { AuditTrail, ConfigPage, Dashboard } from "./pages/compliance/Compliance.jsx";
import { CheckerQueue, ReviewQueue } from "./pages/officer/Queues.jsx";
import Workbench from "./pages/officer/Workbench.jsx";
import { BranchApplication, BranchIntake } from "./pages/officer/Branch.jsx";

const APPLICANT = ["APPLICANT"];
const OFFICER = ["KYC_OFFICER"];
const CHECKER = ["COMPLIANCE_OFFICER"];

function Header() {
  const { user, logout, hasRole } = useAuth();
  if (!user) return null;
  return (
    <header className="header">
      <NavLink to={homeFor(user)} className="brand">OnboardIQ</NavLink>
      <nav>
        {hasRole("APPLICANT") && <NavLink to="/my">My applications</NavLink>}
        {hasRole("KYC_OFFICER") && <NavLink to="/branch">Branch intake</NavLink>}
        {hasRole("KYC_OFFICER") && <NavLink to="/review">Review queue</NavLink>}
        {hasRole("COMPLIANCE_OFFICER") && <NavLink to="/checker">Checker queue</NavLink>}
        {hasRole("COMPLIANCE_OFFICER") && <NavLink to="/dashboard">Dashboard</NavLink>}
        {hasRole("COMPLIANCE_OFFICER") && <NavLink to="/config">Config</NavLink>}
      </nav>
      <span className="user">
        {user.full_name} <span className="muted small">({user.roles.join(", ")})</span>
        <button className="btn btn-small" onClick={logout}>Sign out</button>
      </span>
    </header>
  );
}

export default function App() {
  const { user } = useAuth();
  const guard = (roles, el) => <RequireRole roles={roles}>{el}</RequireRole>;
  return (
    <div className="layout">
      <Header />
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to={homeFor(user)} replace />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/my" element={guard(APPLICANT, <MyApplications />)} />
          <Route path="/apply" element={guard(APPLICANT, <ApplyForm />)} />
          <Route path="/my/:id" element={guard(APPLICANT, <ApplicationDetail />)} />
          <Route path="/branch" element={guard(OFFICER, <BranchIntake />)} />
          <Route path="/branch/new" element={guard(OFFICER, <ApplyForm mode="branch" />)} />
          <Route path="/branch/:id" element={guard(OFFICER, <BranchApplication />)} />
          <Route path="/review" element={guard(OFFICER, <ReviewQueue />)} />
          <Route path="/review/:id" element={guard(OFFICER, <Workbench mode="officer" />)} />
          <Route path="/checker" element={guard(CHECKER, <CheckerQueue />)} />
          <Route path="/checker/:id" element={guard(CHECKER, <Workbench mode="checker" />)} />
          <Route path="/dashboard" element={guard(CHECKER, <Dashboard />)} />
          <Route path="/audit/:id" element={guard(CHECKER, <AuditTrail />)} />
          <Route path="/config" element={guard(CHECKER, <ConfigPage />)} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
