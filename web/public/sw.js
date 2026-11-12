/* ECHO service worker: the part that runs when the tab is closed.
 *
 * It does two things, both of them deliberately small.
 *
 * 1. `push` — a notification arrives encrypted, is decrypted by the browser, and is
 *    shown. The payload is untrusted input, so every field is type-checked and the
 *    navigation target is forced to a same-origin path: a compromised or buggy sender
 *    must not be able to point the notification at somewhere else.
 * 2. `notificationclick` — focus an existing tab and navigate it, or open one.
 *
 * No caching, no offline shell, no fetch interception. A service worker that sits in
 * front of every request is a memory engine's worst neighbour: a stale cache would
 * serve yesterday's vault.
 */

const FALLBACK = {
  title: 'ECHO',
  body: 'You asked to be reminded about something.',
  url: '/reminders',
  tag: 'echo',
};

function safePath(candidate) {
  if (typeof candidate !== 'string') return FALLBACK.url;
  // Same-origin relative paths only: no absolute URLs, no protocol-relative, no CRLF.
  if (!candidate.startsWith('/') || candidate.startsWith('//')) return FALLBACK.url;
  if (/[\r\n]/.test(candidate)) return FALLBACK.url;
  return candidate;
}

function readPayload(event) {
  if (!event.data) return { ...FALLBACK };
  let parsed = null;
  try {
    parsed = event.data.json();
  } catch {
    try {
      parsed = { body: event.data.text() };
    } catch {
      parsed = null;
    }
  }
  if (!parsed || typeof parsed !== 'object') return { ...FALLBACK };
  return {
    title: typeof parsed.title === 'string' && parsed.title.trim() ? parsed.title.slice(0, 120) : FALLBACK.title,
    body: typeof parsed.body === 'string' ? parsed.body.slice(0, 400) : FALLBACK.body,
    url: safePath(parsed.url),
    tag: typeof parsed.tag === 'string' && parsed.tag.trim() ? parsed.tag.slice(0, 64) : FALLBACK.tag,
  };
}

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  const payload = readPayload(event);
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      tag: payload.tag,
      icon: '/favicon.svg',
      badge: '/favicon.svg',
      data: { url: payload.url },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = safePath(event.notification.data && event.notification.data.url);

  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const client of windows) {
        const url = new URL(client.url);
        if (url.origin !== self.location.origin) continue;
        await client.focus();
        if ('navigate' in client) {
          try {
            await client.navigate(target);
          } catch {
            /* a closed tab is not an error worth surfacing */
          }
        }
        return;
      }
      await self.clients.openWindow(target);
    })(),
  );
});
