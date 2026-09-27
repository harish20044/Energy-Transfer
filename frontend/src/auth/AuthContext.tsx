import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { fetchMe, login as apiLogin, type UserProfile } from '@/api/auth';
import { AuthContext, type AuthContextValue, type AuthStatus } from '@/auth/context';

const ACCESS_TOKEN_KEY = 'energy-transfer.access_token';
const REFRESH_TOKEN_KEY = 'energy-transfer.refresh_token';

/** Read a token synchronously so the very first render already knows whether
 *  a session might exist — avoiding a guaranteed flash of the login page for
 *  every already-signed-in user on every reload. */
function readStoredToken(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    // A private-browsing tab or blocked storage throws rather than returning
    // null; either way, there is no session to restore.
    return null;
  }
}

function storeTokens(accessToken: string, refreshToken: string): void {
  try {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  } catch {
    // Session simply won't survive a reload; login itself still succeeds.
  }
}

function clearStoredTokens(): void {
  try {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // Nothing to clean up if storage was never reachable.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(() =>
    readStoredToken(ACCESS_TOKEN_KEY),
  );
  const [user, setUser] = useState<UserProfile | null>(null);
  const [status, setStatus] = useState<AuthStatus>(accessToken ? 'checking' : 'anonymous');

  const logout = useCallback(() => {
    clearStoredTokens();
    setAccessToken(null);
    setUser(null);
    setStatus('anonymous');
  }, []);

  // On mount (or whenever the token changes), confirm the stored access token
  // still works before trusting it — it may have expired since the last visit.
  useEffect(() => {
    if (accessToken === null) {
      setStatus('anonymous');
      return;
    }

    let cancelled = false;
    setStatus('checking');

    fetchMe(accessToken)
      .then((profile) => {
        if (cancelled) return;
        setUser(profile);
        setStatus('authenticated');
      })
      .catch(() => {
        if (cancelled) return;
        // Token is invalid or expired; refresh isn't wired up yet, so the
        // clean, honest behaviour is to sign the user out rather than loop.
        clearStoredTokens();
        setAccessToken(null);
        setUser(null);
        setStatus('anonymous');
      });

    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await apiLogin({ email, password });
    storeTokens(tokens.access_token, tokens.refresh_token);
    setAccessToken(tokens.access_token);
    // status flips to 'checking' then 'authenticated' via the effect above,
    // which also fetches the profile — one source of truth for "who is this."
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, accessToken, login, logout }),
    [status, user, accessToken, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
