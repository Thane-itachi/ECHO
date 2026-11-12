import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import * as api from './api';
import { ApiError, setToken, getToken, type User } from './api';

interface AuthValue {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signInWithCode: (email: string, password: string, code: string) => Promise<void>;
  /** Register, which sends the verification code. No session yet. */
  signUp: (email: string, password: string) => Promise<void>;
  /** Spend the code from the email and open the vault. */
  verifyEmail: (email: string, code: string) => Promise<void>;
  setEmailOtp: (enabled: boolean) => Promise<void>;
  setReminderEmail: (enabled: boolean) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      if (!getToken()) {
        setLoading(false);
        return;
      }
      try {
        const current = await api.me();
        if (!cancelled) setUser(current);
      } catch {
        setToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const token = await api.signIn(email, password);
    setToken(token);
    const current = await api.me();
    setUser(current);
  }, []);

  const signInWithCode = useCallback(async (email: string, password: string, code: string) => {
    const token = await api.signInWithCode(email, password, code);
    setToken(token);
    setUser(await api.me());
  }, []);

  const signUp = useCallback(async (email: string, password: string) => {
    // Registration proves nothing on its own: the address still has to answer with
    // the six digits ECHO just emailed it.
    await api.register(email, password);
  }, []);

  const verifyEmail = useCallback(async (email: string, code: string) => {
    const token = await api.confirmVerification(email, code);
    setToken(token);
    setUser(await api.me());
  }, []);

  const setEmailOtp = useCallback(async (enabled: boolean) => {
    setUser(await api.setAuthPreferences({ email_otp_enabled: enabled }));
  }, []);

  const setReminderEmail = useCallback(async (enabled: boolean) => {
    setUser(await api.setReminderEmail(enabled));
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ user, loading, signIn, signInWithCode, signUp, verifyEmail, setEmailOtp, setReminderEmail, signOut }),
    [user, loading, signIn, signInWithCode, signUp, verifyEmail, setEmailOtp, setReminderEmail, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}

/** Turn any thrown value into a line of text a person can read. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong.';
}

/** Sign the user out when the API says the token is gone. */
export function useAuthFailureHandler(): (error: unknown) => boolean {
  const { signOut } = useAuth();
  return useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        signOut();
        return true;
      }
      return false;
    },
    [signOut],
  );
}
