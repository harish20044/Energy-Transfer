import { Loader2, Lock, LogIn, Mail, Zap } from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { ApiError } from '@/api/auth';
import { useAuth } from '@/auth/useAuth';

const MICROGRID_NAME = '10-household microgrid';

interface LocationState {
  from?: { pathname: string };
}

export function Login() {
  const { status, login } = useAuth();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already signed in — bounce straight past the login form, back to wherever
  // ProtectedRoute originally redirected the user from.
  if (status === 'authenticated') {
    const state = location.state as LocationState | null;
    return <Navigate to={state?.from?.pathname ?? '/'} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not reach the server. Is it running?',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-stone-100 px-6 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <span className="flex size-11 items-center justify-center rounded-lg bg-stone-900">
            <Zap className="size-6 text-solar-500" strokeWidth={2.25} aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-bold tracking-tight text-stone-900">
              Energy&#8288;-&#8288;Transfer
            </p>
            <p className="text-xs text-stone-500">{MICROGRID_NAME}</p>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
          <h1 className="text-lg font-bold text-stone-900">Sign in</h1>
          <p className="mt-1 text-sm text-stone-500">Access your household's trading dashboard.</p>

          <form className="mt-6 flex flex-col gap-4" onSubmit={(e) => void handleSubmit(e)}>
            <div>
              <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-stone-700">
                Email
              </label>
              <div className="relative">
                <Mail
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-stone-400"
                  aria-hidden="true"
                />
                <input
                  id="email"
                  name="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                  }}
                  placeholder="you@household.example"
                  className="w-full rounded-lg border border-stone-200 py-2 pr-3 pl-9 text-sm text-stone-900 outline-none placeholder:text-stone-400 focus:border-peer-400 focus:ring-2 focus:ring-peer-100"
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-xs font-medium text-stone-700">
                Password
              </label>
              <div className="relative">
                <Lock
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-stone-400"
                  aria-hidden="true"
                />
                <input
                  id="password"
                  name="password"
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                  }}
                  placeholder="••••••••"
                  className="w-full rounded-lg border border-stone-200 py-2 pr-3 pl-9 text-sm text-stone-900 outline-none placeholder:text-stone-400 focus:border-peer-400 focus:ring-2 focus:ring-peer-100"
                />
              </div>
            </div>

            {error !== null && (
              <p
                role="alert"
                className="rounded-lg bg-grid-50 px-3 py-2 text-xs font-medium text-grid-700"
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="mt-1 flex items-center justify-center gap-2 rounded-lg bg-stone-900 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-stone-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <LogIn className="size-4" aria-hidden="true" />
              )}
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-stone-400">
          New here? Register at{' '}
          <code className="rounded bg-stone-200 px-1 py-0.5 font-mono">
            POST /api/v1/auth/register
          </code>{' '}
          — a self-serve sign-up page comes next.
        </p>
      </div>
    </main>
  );
}
