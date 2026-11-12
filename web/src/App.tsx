import { Navigate, Route, Routes } from 'react-router-dom';

import { AdminAuthProvider } from './admin/AdminAuth';
import { EchoMark } from './components/Logo';
import AdminGuard from './admin/AdminGuard';
import AdminShell from './admin/AdminShell';
import AdminLogin from './admin/pages/AdminLogin';
import Admins from './admin/pages/Admins';
import Audit from './admin/pages/Audit';
import Overview from './admin/pages/Overview';
import Security from './admin/pages/Security';
import Users from './admin/pages/Users';
import Layout from './components/Layout';
import { useAuth } from './lib/auth';
import Ask from './pages/Ask';
import Documents from './pages/Documents';
import Login from './pages/Login';
import People from './pages/People';
import Proposals from './pages/Proposals';
import Reminders from './pages/Reminders';
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
      <Route
        path="/admin/login"
        element={
          <AdminAuthProvider>
            <AdminLogin />
          </AdminAuthProvider>
        }
      />
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
          <Route path="/" element={<Navigate to="/vault" replace />} />
          <Route path="/vault" element={<Vault />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/people" element={<People />} />
          <Route path="/proposals" element={<Proposals />} />
          <Route path="/reminders" element={<Reminders />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/login" element={<Navigate to="/vault" replace />} />
          <Route path="*" element={<Navigate to="/vault" replace />} />
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
