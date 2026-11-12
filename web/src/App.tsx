import { Navigate, Route, Routes } from 'react-router-dom';

import Layout from './components/Layout';
import { useAuth } from './lib/auth';
import Ask from './pages/Ask';
import Login from './pages/Login';
import People from './pages/People';
import Proposals from './pages/Proposals';
import Reminders from './pages/Reminders';
import Vault from './pages/Vault';

function Splash() {
  return (
    <div className="splash">
      <div className="wordmark">ECHO</div>
      <p>Opening your vault…</p>
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();

  if (loading) return <Splash />;

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/vault" replace />} />
        <Route path="/vault" element={<Vault />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/people" element={<People />} />
        <Route path="/proposals" element={<Proposals />} />
        <Route path="/reminders" element={<Reminders />} />
        <Route path="/login" element={<Navigate to="/vault" replace />} />
        <Route path="*" element={<Navigate to="/vault" replace />} />
      </Route>
    </Routes>
  );
}
