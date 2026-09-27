import { Loader2 } from 'lucide-react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '@/auth/useAuth';

/** Gate for any route tree that requires a signed-in user.
 *
 * Renders a neutral loading state while the stored token is being verified —
 * never the login form and never the protected content — so a page reload
 * for an already-authenticated user doesn't flash the login screen first.
 */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-100">
        <Loader2 className="size-6 animate-spin text-stone-400" aria-hidden="true" />
      </div>
    );
  }

  if (status === 'anonymous') {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
