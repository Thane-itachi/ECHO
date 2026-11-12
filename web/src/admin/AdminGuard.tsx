import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAdminAuth } from './AdminAuth';
import { EchoMark } from '../components/Logo';

/**
 * Gate for every console screen. A user session is not an admin session: this checks
 * the admin token only, and bounces to the console login when it is missing or expired.
 */
export default function AdminGuard() {
  const { identity, loading } = useAdminAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="splash">
      <EchoMark size={44} className="splash-mark" />
        <div className="wordmark">ECHO</div>
        <p>Checking your administrator session…</p>
      </div>
    );
  }

  if (!identity) return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;

  return <Outlet />;
}
