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
  email_verified: boolean;
  email_otp_enabled: boolean;
  created_at: string;
  /** Local development only, with no mail provider: the code just emailed. */
  dev_code?: string | null;
}

export interface CodeReceipt {
  status: string;
  /** Present only in local development with no mail provider configured. */
  dev_code?: string | null;
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
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
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
    const envelope = (payload as { error?: { code?: string; details?: unknown } } | null)?.error;
    const code = envelope?.code ?? 'error';
    throw new ApiError(response.status, code, describeError(payload, response.status), envelope?.details);
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

export async function signInWithCode(email: string, password: string, code: string): Promise<string> {
  const result = await request<{ access_token: string }>('/auth/token/code', {
    method: 'POST',
    body: { email, password, code },
  });
  return result.access_token;
}

/** Ask for a verification code. The answer never says whether the address exists. */
export function sendVerificationCode(email: string): Promise<CodeReceipt> {
  return request<CodeReceipt>('/auth/verification/send', { method: 'POST', body: { email } });
}

export async function confirmVerification(email: string, code: string): Promise<string> {
  const result = await request<{ access_token: string }>('/auth/verification/confirm', {
    method: 'POST',
    body: { email, code },
  });
  return result.access_token;
}

export function forgotPassword(email: string): Promise<CodeReceipt> {
  return request<CodeReceipt>('/auth/password/forgot', { method: 'POST', body: { email } });
}

export function resetPassword(email: string, code: string, password: string): Promise<CodeReceipt> {
  return request<CodeReceipt>('/auth/password/reset', { method: 'POST', body: { email, code, password } });
}

export function setAuthPreferences(input: { email_otp_enabled: boolean }): Promise<User> {
  return request<User>('/auth/preferences', { method: 'PATCH', body: input });
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

/* -------------------------------------------------------- notifications --- */

export interface PushKey {
  enabled: boolean;
  public_key: string | null;
}

export interface PushDevice {
  id: string;
  label: string;
  created_at: string;
  last_success_at: string | null;
}

export interface PushDevices {
  enabled: boolean;
  count: number;
  devices: PushDevice[];
}

export interface TestNotification {
  attempted: number;
  sent: number;
  pruned: number;
  failed: number;
}

export function getPushKey(): Promise<PushKey> {
  return request<PushKey>('/push/key');
}

export function listPushDevices(): Promise<PushDevices> {
  return request<PushDevices>('/push/subscriptions');
}

export function subscribePush(input: {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}): Promise<{ id: string; label: string; count: number }> {
  return request('/push/subscribe', { method: 'POST', body: input });
}

export function unsubscribePush(endpoint: string): Promise<{ removed: boolean; count: number }> {
  return request('/push/unsubscribe', { method: 'POST', body: { endpoint } });
}

export function sendTestNotification(): Promise<TestNotification> {
  return request<TestNotification>('/push/test', { method: 'POST' });
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


/* --------------------------------------------------------------- ask 🗣 ---- */

export interface Citation {
  memory_id: string;
  title: string;
  created_at: string;
}

export interface AskAnswer {
  question: string;
  answer: string;
  citations: Citation[];
  mode: string;
  matched: number;
}

/** Ask ECHO: a grounded answer plus the memories it came from. */
export function ask(question: string): Promise<AskAnswer> {
  return request<AskAnswer>('/ask', { method: 'POST', body: { question } });
}

/* ---------------------------------------------------------- captures 📥 ---- */

export interface CaptureQueued {
  job_id: string;
  queued: boolean;
}

/** Paste a note; the worker turns it into proposals. Nothing is filed directly. */
export function createCapture(text: string): Promise<CaptureQueued> {
  return request<CaptureQueued>('/captures', { method: 'POST', body: { text } });
}

/* --------------------------------------------------------- documents 📎 ---- */

export interface Document {
  id: string;
  filename: string;
  size_bytes: number;
  content_type: string | null;
  memory_id: string | null;
  created_at: string;
}

export function listDocuments(): Promise<Page<Document>> {
  return request<Page<Document>>('/documents?limit=100');
}

export async function uploadDocument(file: File, memoryId?: string | null): Promise<Document> {
  const form = new FormData();
  form.append('file', file);
  if (memoryId) form.append('memory_id', memoryId);
  const token = getToken();
  const response = await fetch('/api/documents', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, 'upload_failed', describeError(payload, response.status));
  }
  return payload as Document;
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/documents/${id}`, { method: 'DELETE' });
}

/** Fetch the decrypted bytes and hand the browser a temporary object URL. */
export async function downloadDocument(id: string, filename: string): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/documents/${id}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) throw new ApiError(response.status, 'download_failed', 'That file could not be downloaded.');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/* ------------------------------------------------------------- links 🔗 ---- */

export interface LinkedMemory {
  id: string;
  title: string;
  kind: string;
}

export function listLinks(memoryId: string): Promise<{ items: LinkedMemory[] }> {
  return request<{ items: LinkedMemory[] }>(`/memories/${memoryId}/links`);
}

export function createLink(memoryId: string, toMemoryId: string, kind = 'related'): Promise<{ items: LinkedMemory[] }> {
  return request<{ items: LinkedMemory[] }>(`/memories/${memoryId}/links`, {
    method: 'POST',
    body: { to_memory_id: toMemoryId, kind },
  });
}

export function removeLink(memoryId: string, otherId: string): Promise<{ items: LinkedMemory[] }> {
  return request<{ items: LinkedMemory[] }>(`/memories/${memoryId}/links/${otherId}`, { method: 'DELETE' });
}
