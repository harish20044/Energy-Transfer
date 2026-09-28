import { Outlet } from 'react-router-dom';

import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { LiveDataProvider } from '@/live/LiveDataProvider';

export function AppShell() {
  return (
    <LiveDataProvider>
      <div className="flex h-screen overflow-hidden bg-stone-100">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <main className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </LiveDataProvider>
  );
}
