/**
 * Notifications on this device (Web Push).
 *
 * The honest constraints, because they decide the UI:
 *
 * - The browser decides, not the app. Permission can be `denied` and only the user can
 *   undo that in browser settings, so the toggle says so instead of retrying.
 * - On iPhone and iPad, Safari only allows web push for a site added to the Home
 *   Screen. In an ordinary tab the APIs are simply absent, which is indistinguishable
 *   from "unsupported" unless we look at the user agent.
 * - A subscription is per browser, per device. Enabling on a phone and a laptop gives
 *   two rows, and both get notified.
 */
import {
  ApiError,
  getPushKey,
  listPushDevices,
  subscribePush,
  unsubscribePush,
} from './api';

export type NotificationState =
  | { kind: 'unsupported'; detail: string }
  | { kind: 'ios-not-installed' }
  | { kind: 'server-off' }
  | { kind: 'blocked' }
  | { kind: 'off' }
  | { kind: 'on'; devices: number; label: string | null };

function isIos(): boolean {
  const agent = navigator.userAgent;
  if (/iPad|iPhone|iPod/.test(agent)) return true;
  // iPadOS 13+ reports itself as a Mac; the touch points give it away.
  return /Macintosh/.test(agent) && navigator.maxTouchPoints > 1;
}

function isStandalone(): boolean {
  const iosStandalone = (navigator as Navigator & { standalone?: boolean }).standalone;
  return iosStandalone === true || window.matchMedia('(display-mode: standalone)').matches;
}

function supported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

/** VAPID keys arrive base64url; the Push API wants raw bytes, not a string. */
function decodeKey(value: string): ArrayBuffer {
  const padded = (value + '='.repeat((4 - (value.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes.buffer;
}

async function registration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration('/');
  if (existing?.active) return existing;
  if (!existing) await navigator.serviceWorker.register('/sw.js', { scope: '/' });
  // `register()` resolves while the worker is still *installing*, and subscribing from
  // an inactive worker fails with "no active Service Worker". `ready` waits for the
  // worker that actually controls the page.
  return navigator.serviceWorker.ready;
}

async function currentSubscription(): Promise<PushSubscription | null> {
  if (!supported()) return null;
  const ready = await navigator.serviceWorker.getRegistration('/');
  if (!ready) return null;
  return ready.pushManager.getSubscription();
}

/** What the toggle should show, without changing anything. */
export async function notificationState(): Promise<NotificationState> {
  if (!supported()) {
    if (isIos() && !isStandalone()) return { kind: 'ios-not-installed' };
    return {
      kind: 'unsupported',
      detail: 'This browser cannot receive notifications. Chrome, Edge or Firefox can.',
    };
  }
  if (isIos() && !isStandalone()) return { kind: 'ios-not-installed' };

  const subscription = await currentSubscription();
  if (Notification.permission === 'denied') return { kind: 'blocked' };

  const key = await getPushKey().catch(() => null);
  if (!key?.enabled) return { kind: 'server-off' };

  if (!subscription) return { kind: 'off' };

  // Subscribed in this browser: confirm the server still knows about it, because a
  // deployment that changed keys leaves the local subscription orphaned.
  const devices = await listPushDevices().catch(() => null);
  if (!devices || devices.count === 0) return { kind: 'off' };
  return { kind: 'on', devices: devices.count, label: devices.devices[0]?.label ?? null };
}

/**
 * Ask for permission and register this browser.
 *
 * Order matters: the permission prompt must come from a user gesture, and the push
 * service must be reachable before the server is told about an endpoint it cannot use.
 */
export async function enableNotifications(): Promise<NotificationState> {
  if (!supported()) throw new ApiError(0, 'unsupported', 'This browser cannot receive notifications.');

  const key = await getPushKey();
  if (!key.enabled || !key.public_key) {
    throw new ApiError(503, 'push_not_configured', 'Notifications are not configured on this server.');
  }

  if (Notification.permission === 'denied') {
    throw new ApiError(403, 'blocked', 'Notifications are blocked for this site in your browser settings.');
  }

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    throw new ApiError(403, 'blocked', 'Notifications were not allowed, so nothing was enabled.');
  }

  const ready = await registration();
  let subscription = await ready.pushManager.getSubscription();
  if (!subscription) {
    try {
      subscription = await ready.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: decodeKey(key.public_key),
      });
    } catch (caught) {
      const reason = caught instanceof Error ? caught.message : 'the browser refused';
      throw new ApiError(
        0,
        'subscribe_failed',
        `This browser could not register for notifications (${reason}). Reload the page and try again.`,
      );
    }
  }

  const json = subscription.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
  if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) {
    throw new ApiError(0, 'bad_subscription', 'The browser returned an incomplete subscription.');
  }

  const created = await subscribePush({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
  });
  return { kind: 'on', devices: created.count, label: created.label };
}

/** Stop notifications on this device only. Other devices are untouched. */
export async function disableNotifications(): Promise<NotificationState> {
  const subscription = await currentSubscription();
  if (!subscription) return { kind: 'off' };
  const endpoint = subscription.endpoint;
  try {
    await unsubscribePush(endpoint);
  } finally {
    // Even if the server call failed, the browser must stop receiving: a phone that
    // keeps buzzing after "turn off" is worse than a stale row.
    await subscription.unsubscribe().catch(() => undefined);
  }
  return { kind: 'off' };
}
