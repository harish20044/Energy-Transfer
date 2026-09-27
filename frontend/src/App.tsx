import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/components/layout/AppShell';
import { AuthProvider } from '@/auth/AuthContext';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { Dashboard } from '@/pages/Dashboard';
import { Login } from '@/pages/Login';
import { Market } from '@/pages/Market';
import { Network } from '@/pages/Network';
import { Settings } from '@/pages/Settings';
import { Trades } from '@/pages/Trades';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route index element={<Dashboard />} />
              <Route path="market" element={<Market />} />
              <Route path="network" element={<Network />} />
              <Route path="trades" element={<Trades />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
