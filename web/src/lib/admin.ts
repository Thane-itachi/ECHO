/**
 * Admin console client.
 *
 * Deliberately a separate module with a **separate token key**. An admin token is a
 * different audience with a fifteen-minute life and MFA behind it; keeping it out of
 * `echo.token` means a stolen user session is never an admin session, and signing out
 * of the vault does not silently leave an admin token in localStorage.
 */

import { ApiError } from './api';

const ADMIN_TOKEN_KEY = 'echo.admin.token';

export interface AdminIdentity {
  id: string;
  email: string;
  role: AdminRole;
  permissions: string[];
}

export type AdminRole = 'founder' | 'platform_admin' | 'support_admin';

export interface PlatformStats {
  users_total: number;
  users_active: number;
  memories_total: number;
  proposals_pending: number;
  outbox_pending: number;
}

export interface Health {
  status: string;
  database: string;
  jobs_queued: number;
  jobs_failed: number;
  outbox_pending: number;
  admins_active: number;
  admins_without_recent_login: number;
}

export interface AnalyticsPoint {
  day: string;
  users: number;
  memories: number;
  proposals: number;
}

export interface Analytics {
  window_days: number;
  points: AnalyticsPoint[];
  proposals_approved: number;
  proposals_rejected: number;
  approval_rate: number | null;
}

export interface SecurityEvent {
  action: string;
  actor_type: string;
  actor_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface Security {
  failed_admin_logins_24h: number;
  failed_user_logins_24h: number;
  disabled_admins: number;
  inactive_users: number;
  recent_events: SecurityEvent[];
}

export interface AccountRow {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface AdminAccount extends AccountRow {
  role: AdminRole;
  last_login_at: string | null;
}

export interface AdminAccountCreated extends AdminAccount {
  totp_secret: string;
  otpauth_url: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  actor_type: string;
  actor_id: string | null;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export function getAdminToken(): string | null {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAdminToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token);
    else localStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    /* private mode: the admin session simply will not persist */
  }
}

async function request<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const { method = 'GET', body } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = getAdminToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`/admin${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the ECHO server. Is the API running?');
  }

  if (response.status === 401) setAdminToken(null);
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message =
      (payload as { error?: { message?: string } } | null)?.error?.message ?? `Request failed (${response.status})`;
    throw new ApiError(response.status, 'admin_error', message);
  }
  return payload as T;
}

export async function signIn(email: string, password: string, totpCode: string): Promise<string> {
  const result = await request<{ access_token: string }>('/auth/token', {
    method: 'POST',
    body: { email, password, totp_code: totpCode },
  });
  setAdminToken(result.access_token);
  return result.access_token;
}

export function identity(): Promise<AdminIdentity> {
  return request<AdminIdentity>('/me');
}

export function stats(): Promise<PlatformStats> {
  return request<PlatformStats>('/stats');
}

export function health(): Promise<Health> {
  return request<Health>('/health');
}

export function analytics(days = 14): Promise<Analytics> {
  return request<Analytics>(`/analytics?days=${days}`);
}

export function security(): Promise<Security> {
  return request<Security>('/security');
}

export function listUsers(): Promise<{ items: AccountRow[]; total: number }> {
  return request<{ items: AccountRow[]; total: number }>('/users?limit=200');
}

export function setUserActive(userId: string, isActive: boolean): Promise<AccountRow> {
  return request<AccountRow>(`/users/${userId}/status`, { method: 'POST', body: { is_active: isActive } });
}

export function listAdmins(): Promise<{ items: AdminAccount[]; total: number }> {
  return request<{ items: AdminAccount[]; total: number }>('/admins');
}

export function createAdmin(email: string, password: string, role: AdminRole): Promise<AdminAccountCreated> {
  return request<AdminAccountCreated>('/admins', { method: 'POST', body: { email, password, role } });
}

export function setAdminRole(adminId: string, role: AdminRole): Promise<AdminAccount> {
  return request<AdminAccount>(`/admins/${adminId}/role`, { method: 'PATCH', body: { role } });
}

export function setAdminActive(adminId: string, isActive: boolean): Promise<AdminAccount> {
  return request<AdminAccount>(`/admins/${adminId}/status`, { method: 'POST', body: { is_active: isActive } });
}

export function rotateAdminMfa(adminId: string): Promise<AdminAccountCreated> {
  return request<AdminAccountCreated>(`/admins/${adminId}/mfa/rotate`, { method: 'POST' });
}

export function audit(limit = 100): Promise<{ items: AuditEntry[]; total: number }> {
  return request<{ items: AuditEntry[]; total: number }>(`/audit?limit=${limit}`);
}

export function emergencyAccess(reason: string): Promise<{ access_token: string; expires_in: number }> {
  return request<{ access_token: string; expires_in: number }>('/emergency/access', {
    method: 'POST',
    body: { reason },
  });
}
