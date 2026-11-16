import { Navigate, Route, Routes } from 'react-router-dom';

import { AdminAuthProvider } from './admin/AdminAuth';
import { EchoMark } from './components/Logo';
import AdminGuard from './admin/AdminGuard';
import AdminShell from './admin/AdminShell';
import AdminEnrol from './admin/pages/AdminEnrol';
import AdminLogin from './admin/pages/AdminLogin';
import Admins from './admin/pages/Admins';
import Audit from './admin/pages/Audit';
import Overview from './admin/pages/Overview';
import Security from './admin/pages/Security';
import Users from './admin/pages/Users';
import Layout from './components/Layout';
import PublicLayout from './components/PublicLayout';
import { useAuth } from './lib/auth';
import Ask from './pages/Ask';
import Dashboard from './pages/Dashboard';
import Documents from './pages/Documents';
import Help from './pages/Help';
import Home from './pages/Home';
import HowItWorks from './pages/HowItWorks';
import Login from './pages/Login';
import People from './pages/People';
import Privacy from './pages/Privacy';
import Proposals from './pages/Proposals';
import Profile from './pages/Profile';
import Reminders from './pages/Reminders';
import Reports from './pages/Reports';
import Search from './pages/Search';
import AccountSecurity from './pages/Security';
import Settings from './pages/Settings';
import Vault from './pages/Vault';

function Splash() {
  return (
    <div className="splash">
      <EchoMark size={44} className="splash-mark" />
      <div className="wordmark">ECHO</div>
      <p>Opening your vault…</p>
    </div>
  );
}

/**
 * One route tree for the whole app. The console routes live here (not inside a nested
 * <Routes>) and are wrapped in their own provider, so an admin session and a user
 * session can never share state or tokens.
 */
export default function App() {
  const { user, loading } = useAuth();

  return (
    <Routes>
      {/* The four pages anyone can read, signed in or not. They come before the
          guards so a visitor without an account never lands inside the app. */}
      <Route element={<PublicLayout />}>
        <Route path="/" element={<Home />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/help" element={<Help />} />
      </Route>

      <Route
        path="/admin/login"
        element={
          <AdminAuthProvider>
            <AdminLogin />
          </AdminAuthProvider>
        }
      />
      {/* Public by design: the token in the link is the credential, and the page
          cannot reach anything in the console without a verified code. */}
      <Route path="/admin/enrol" element={<AdminEnrol />} />
      <Route
        path="/admin"
        element={
          <AdminAuthProvider>
            <AdminGuard />
          </AdminAuthProvider>
        }
      >
        <Route element={<AdminShell />}>
          <Route index element={<Overview />} />
          <Route path="users" element={<Users />} />
          <Route path="admins" element={<Admins />} />
          <Route path="audit" element={<Audit />} />
          <Route path="security" element={<Security />} />
        </Route>
      </Route>

      {loading ? (
        <Route path="*" element={<Splash />} />
      ) : user ? (
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/vault" element={<Vault />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/people" element={<People />} />
          <Route path="/proposals" element={<Proposals />} />
          <Route path="/reminders" element={<Reminders />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/search" element={<Search />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/security" element={<AccountSecurity />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/login" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      ) : (
        <>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </>
      )}
    </Routes>
  );
}
