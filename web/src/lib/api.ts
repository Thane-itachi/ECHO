/**
 * Typed client for the ECHO API.
 *
 * The token lives in localStorage for now. That is a deliberate, written-down
 * tradeoff for a same-origin SPA; moving to httpOnly cookies + CSRF is a one-file
 * change (`request`) and is on the Milestone 3 list.
 */

export const CATEGORIES = [
  'people',
  'belongings',
  'work',
  'clients',
  'documents',
  'promises',
  'maintenance',
  'plans',
  'events',
  'general',
] as const;

export type Category = (typeof CATEGORIES)[number];
export type ProposalStatus = 'pending' | 'approved' | 'rejected';

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface Memory {
  id: string;
  title: string;
  content: string;
  category: Category;
  person_id: string | null;
  source: string;
  confidence: number | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Person {
  id: string;
  name: string;
  notes: string | null;
  created_at: string;
}

export interface Proposal {
  id: string;
  status: ProposalStatus;
  title: string;
  content: string;
  source_text: string;
  category: Category;
  confidence: number | null;
  memory_id: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface Reminder {
  id: string;
  title: string;
  due_at: string;
  status: string;
  memory_id: string | null;
  created_at: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

const TOKEN_KEY = 'echo.token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the session simply will not persist across reloads */
  }
}

interface ValidationDetail {
  loc?: (string | number)[];
  msg?: string;
}

function describeError(payload: unknown, status: number): string {
  const error = (payload as { error?: { message?: string; code?: string; details?: unknown } } | null)?.error;
  if (!error) return `Request failed (${status})`;
  if (error.code === 'validation_error' && Array.isArray(error.details)) {
    const first = (error.details as ValidationDetail[])[0];
    if (first?.msg) {
      const field = (first.loc ?? []).filter((part) => part !== 'body').join('.');
      return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  return error.message ?? `Request failed (${status})`;
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const { method = 'GET', body, signal } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error;
    throw new ApiError(0, 'network_error', 'Cannot reach the ECHO server. Is the API running?');
  }

  if (response.status === 401) setToken(null);
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const code = (payload as { error?: { code?: string } } | null)?.error?.code ?? 'error';
    throw new ApiError(response.status, code, describeError(payload, response.status));
  }
  return payload as T;
}

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    search.set(key, String(value));
  }
  const serialised = search.toString();
  return serialised ? `?${serialised}` : '';
}

/* ---------------------------------------------------------------- auth ---- */

export function register(email: string, password: string): Promise<User> {
  return request<User>('/auth/register', { method: 'POST', body: { email, password } });
}

export async function signIn(email: string, password: string): Promise<string> {
  const result = await request<{ access_token: string }>('/auth/token', {
    method: 'POST',
    body: { email, password },
  });
  return result.access_token;
}

export function me(): Promise<User> {
  return request<User>('/auth/me');
}

/* ------------------------------------------------------------- memories ---- */

export interface MemoryQuery {
  q?: string;
  category?: Category | '';
  include_archived?: boolean;
  limit?: number;
  offset?: number;
}

export function listMemories(params: MemoryQuery = {}): Promise<Page<Memory>> {
  return request<Page<Memory>>(`/memories${query({ ...params })}`);
}

export function createMemory(input: {
  title: string;
  content: string;
  category: Category;
  person_id?: string | null;
}): Promise<Memory> {
  return request<Memory>('/memories', { method: 'POST', body: input });
}

export function updateMemory(
  id: string,
  input: { title?: string; content?: string; category?: Category; person_id?: string | null },
): Promise<Memory> {
  return request<Memory>(`/memories/${id}`, { method: 'PATCH', body: input });
}

export function deleteMemory(id: string): Promise<void> {
  return request<void>(`/memories/${id}`, { method: 'DELETE' });
}

export function archiveMemory(id: string): Promise<Memory> {
  return request<Memory>(`/memories/${id}/archive`, { method: 'POST' });
}

export function restoreMemory(id: string): Promise<Memory> {
  return request<Memory>(`/memories/${id}/restore`, { method: 'POST' });
}

/* --------------------------------------------------------------- people --- */

export function listPeople(): Promise<Page<Person>> {
  return request<Page<Person>>('/people?limit=200');
}

export function createPerson(input: { name: string; notes?: string }): Promise<Person> {
  return request<Person>('/people', { method: 'POST', body: input });
}

export function deletePerson(id: string): Promise<void> {
  return request<void>(`/people/${id}`, { method: 'DELETE' });
}

/* ------------------------------------------------------------ proposals --- */

export function listProposals(status?: ProposalStatus): Promise<Page<Proposal>> {
  return request<Page<Proposal>>(`/proposals${query({ status, limit: 100 })}`);
}

export function createProposal(input: {
  title: string;
  content: string;
  source_text: string;
  category: Category;
  confidence?: number;
}): Promise<Proposal> {
  return request<Proposal>('/proposals', { method: 'POST', body: input });
}

export function approveProposal(id: string): Promise<{ proposal: Proposal; memory: Memory | null }> {
  return request<{ proposal: Proposal; memory: Memory | null }>(`/proposals/${id}/approve`, { method: 'POST' });
}

export function rejectProposal(id: string): Promise<{ proposal: Proposal; memory: Memory | null }> {
  return request<{ proposal: Proposal; memory: Memory | null }>(`/proposals/${id}/reject`, { method: 'POST' });
}

/* ------------------------------------------------------------ reminders --- */

export function listReminders(): Promise<Page<Reminder>> {
  return request<Page<Reminder>>('/reminders?limit=200');
}

export function createReminder(input: {
  title: string;
  due_at: string;
  memory_id?: string | null;
}): Promise<Reminder> {
  return request<Reminder>('/reminders', { method: 'POST', body: input });
}

export function cancelReminder(id: string): Promise<Reminder> {
  return request<Reminder>(`/reminders/${id}/cancel`, { method: 'POST' });
}

/* ---------------------------------------------------------------- dates --- */

/** The API stores naive UTC; parse it as UTC rather than as browser-local time. */
export function parseUtc(iso: string): Date {
  if (/[zZ]$|[+-]\d{2}:\d{2}$/.test(iso)) return new Date(iso);
  return new Date(`${iso}Z`);
}

export function formatDate(iso: string): string {
  return parseUtc(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function formatDateTime(iso: string): string {
  return parseUtc(iso).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function relativeDue(iso: string): string {
  const target = parseUtc(iso).getTime();
  const diff = target - Date.now();
  const abs = Math.abs(diff);
  const minutes = Math.round(abs / 60_000);
  const hours = Math.round(abs / 3_600_000);
  const days = Math.round(abs / 86_400_000);
  const amount = days >= 1 ? `${days} day${days === 1 ? '' : 's'}` : hours >= 1 ? `${hours}h` : `${minutes}m`;
  return diff >= 0 ? `in ${amount}` : `${amount} ago`;
}

export function toDateTimeLocal(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}`;
}
