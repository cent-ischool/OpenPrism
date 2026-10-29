/**
 * Session state and the authenticated fetch used by every API call.
 *
 * Two kinds of credential exist:
 *  - an account session: JWT access + refresh tokens in localStorage (shared by tabs);
 *  - a guest invite token: set by opening an invite link, kept in sessionStorage so it only affects that tab.
 * The invite token wins while present (a tab that joined through a link acts as that guest until it leaves).
 *
 * Tokens in localStorage are readable by any script on the page, so the app must never inject untrusted HTML.
 * The short access-token lifetime (30 min) and refresh-token rotation (the server revokes each used refresh token)
 * limit what a stolen token is worth.
 */
const SESSION_KEY = 'openprism-auth-v1';
const INVITE_KEY = 'openprism-collab-token';
const LANG_KEY = 'openprism-lang';
const REFRESH_MARGIN_MS = 60_000;

export interface Session {
  access: string;
  refresh: string;
}

type Listener = () => void;
const listeners = new Set<Listener>();
let refreshInFlight: Promise<boolean> | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;

function notify() {
  listeners.forEach((l) => l());
}

/** Subscribe to credential changes (sign-in, sign-out, token refresh, other tabs). Returns an unsubscribe function. */
export function subscribeSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function readSession(): Session | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Session>;
    return parsed.access && parsed.refresh ? { access: parsed.access, refresh: parsed.refresh } : null;
  } catch {
    return null;
  }
}

export function getSession(): Session | null {
  return typeof window === 'undefined' ? null : readSession();
}

export function setSession(session: Session) {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  scheduleRefresh();
  notify();
}

export function clearSession() {
  window.localStorage.removeItem(SESSION_KEY);
  if (refreshTimer) clearTimeout(refreshTimer);
  notify();
}

export function getInviteToken(): string {
  return typeof window === 'undefined' ? '' : window.sessionStorage.getItem(INVITE_KEY) || '';
}

export function setInviteToken(token: string) {
  if (!token) return;
  window.sessionStorage.setItem(INVITE_KEY, token);
  notify();
}

export function clearInviteToken() {
  window.sessionStorage.removeItem(INVITE_KEY);
  notify();
}

/** The credential for this tab, as a bearer token. */
export function currentToken(): string {
  return getInviteToken() || getSession()?.access || '';
}

/** Token to put in a URL's `?token=` (img/object/EventSource/WebSocket cannot send headers). */
export const tokenForUrl = currentToken;

export function authHeaders(): Record<string, string> {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function langHeader(): string {
  if (typeof window === 'undefined') return 'en-US';
  return window.localStorage.getItem(LANG_KEY) === 'zh-CN' ? 'zh-CN' : 'en-US';
}

function expiryOf(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]!.replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Refresh shortly before the access token expires so long-lived connections (collab) keep a valid token. */
function scheduleRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer);
  const session = readSession();
  const exp = session && expiryOf(session.access);
  if (!exp) return;
  const delay = Math.max(5_000, exp - Date.now() - REFRESH_MARGIN_MS);
  refreshTimer = setTimeout(() => void refreshSession(), delay);
}

/** Exchange the refresh token for new tokens. Concurrent callers share one request. Signs out if it is rejected. */
export function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const session = readSession();
  if (!session) return Promise.resolve(false);
  refreshInFlight = (async () => {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: session.refresh })
      });
      if (res.status === 401 || res.status === 400) {
        clearSession(); // revoked or expired: the account must sign in again
        return false;
      }
      if (!res.ok) return false; // server trouble: keep the session and retry later
      const data = (await res.json()) as { access: string; refresh?: string };
      setSession({ access: data.access, refresh: data.refresh || session.refresh });
      return true;
    } catch {
      return false; // offline: keep the session
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** Start background token refresh and cross-tab sync. Call once at startup. */
export function initSession() {
  scheduleRefresh();
  window.addEventListener('storage', (e) => {
    if (e.key === SESSION_KEY) {
      scheduleRefresh();
      notify();
    }
  });
}

/**
 * fetch() with the language header and the right credential. If an account's access token has expired it is
 * refreshed once and the request is retried; guests (invite tokens) do not refresh.
 */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const build = () => {
    const headers = new Headers(init.headers);
    if (!headers.has('x-lang')) headers.set('x-lang', langHeader());
    if (!headers.has('Authorization')) {
      Object.entries(authHeaders()).forEach(([k, v]) => headers.set(k, v));
    }
    return { ...init, headers };
  };
  const res = await fetch(input, build());
  if (res.status === 401 && !getInviteToken() && getSession() && (await refreshSession())) {
    return fetch(input, build());
  }
  return res;
}
