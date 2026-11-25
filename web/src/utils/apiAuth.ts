const AUTH_STORAGE_KEY = 'quasar-web-token';
const AUTH_QUERY_KEYS = ['token', 'quasar_token'];

declare global {
  interface Window {
    __quasarAuthFetchInstalled?: boolean;
  }
}

function consumeTokenFromUrl(): string {
  if (typeof window === 'undefined') return '';

  const url = new URL(window.location.href);
  const token = AUTH_QUERY_KEYS.map(key => url.searchParams.get(key)).find(Boolean) || '';
  if (!token) {
    return '';
  }

  localStorage.setItem(AUTH_STORAGE_KEY, token);
  AUTH_QUERY_KEYS.forEach(key => url.searchParams.delete(key));
  window.history.replaceState(window.history.state, document.title, `${url.pathname}${url.search}${url.hash}`);
  return token;
}

export function getWebAuthToken(): string {
  if (typeof window === 'undefined') return '';
  return consumeTokenFromUrl() || localStorage.getItem(AUTH_STORAGE_KEY) || '';
}

function isApiUrl(input: RequestInfo | URL): boolean {
  const rawUrl = input instanceof Request ? input.url : input.toString();
  return new URL(rawUrl, window.location.origin).pathname.startsWith('/api/');
}

export function withAuthUrl(rawUrl: string): string {
  if (typeof window === 'undefined') return rawUrl;

  const token = getWebAuthToken();
  if (!token) return rawUrl;

  const url = new URL(rawUrl, window.location.origin);
  if (!url.pathname.startsWith('/api/') && url.protocol !== 'ws:' && url.protocol !== 'wss:') {
    return rawUrl;
  }

  url.searchParams.set('token', token);
  return url.origin === window.location.origin
    ? `${url.pathname}${url.search}${url.hash}`
    : url.toString();
}

export function withAuthWebSocketUrl(rawUrl: string): string {
  const token = getWebAuthToken();
  if (!token) return rawUrl;

  const url = new URL(rawUrl);
  url.searchParams.set('token', token);
  return url.toString();
}

export function installAuthenticatedFetch(): void {
  if (typeof window === 'undefined' || window.__quasarAuthFetchInstalled) {
    return;
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    if (!isApiUrl(input)) {
      return nativeFetch(input, init);
    }

    const token = getWebAuthToken();
    if (!token) {
      return nativeFetch(input, init);
    }

    const requestHeaders = input instanceof Request ? input.headers : undefined;
    const headers = new Headers(requestHeaders);
    new Headers(init.headers).forEach((value, key) => headers.set(key, value));

    if (!headers.has('authorization') && !headers.has('x-quasar-web-token')) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    return nativeFetch(input, { ...init, headers });
  };

  window.__quasarAuthFetchInstalled = true;
}

