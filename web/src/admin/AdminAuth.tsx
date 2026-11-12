import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import * as adminApi from '../lib/admin';
import { ApiError } from '../lib/api';

interface AdminAuthValue {
  identity: adminApi.AdminIdentity | null;
  loading: boolean;
  signIn: (email: string, password: string, totp: string) => Promise<void>;
  signOut: () => void;
  can: (permission: string) => boolean;
}

const AdminAuthContext = createContext<AdminAuthValue | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<adminApi.AdminIdentity | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      if (!adminApi.getAdminToken()) {
        setLoading(false);
        return;
      }
      try {
        const current = await adminApi.identity();
        if (!cancelled) setIdentity(current);
      } catch {
        adminApi.setAdminToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string, totp: string) => {
    await adminApi.signIn(email, password, totp);
    setIdentity(await adminApi.identity());
  }, []);

  const signOut = useCallback(() => {
    adminApi.setAdminToken(null);
    setIdentity(null);
  }, []);

  const can = useCallback(
    (permission: string) => Boolean(identity?.permissions.includes(permission)),
    [identity],
  );

  const value = useMemo<AdminAuthValue>(
    () => ({ identity, loading, signIn, signOut, can }),
    [identity, loading, signIn, signOut, can],
  );

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}

export function useAdminAuth(): AdminAuthValue {
  const context = useContext(AdminAuthContext);
  if (!context) throw new Error('useAdminAuth must be used inside AdminAuthProvider');
  return context;
}

export function adminErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong.';
}
