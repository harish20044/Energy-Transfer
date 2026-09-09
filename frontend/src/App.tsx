import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/components/layout/AppShell';
import { Dashboard } from '@/pages/Dashboard';
import { Market } from '@/pages/Market';
import { Network } from '@/pages/Network';
import { Settings } from '@/pages/Settings';
import { Trades } from '@/pages/Trades';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="market" element={<Market />} />
          <Route path="network" element={<Network />} />
          <Route path="trades" element={<Trades />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
