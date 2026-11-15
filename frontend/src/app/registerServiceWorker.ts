// frontend/src/app/registerServiceWorker.ts

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/**
 * Register the service worker (public/sw.js) in production builds on a real
 * domain. Skipped in development (always fresh code) and on localhost, where
 * Caddy's local certificate isn't trusted and browsers refuse the worker.
 * Failure is harmless: the app works without it.
 *
 * @returns Whether registration was attempted.
 */
export function registerServiceWorker(
  isProduction: boolean = import.meta.env.PROD,
  nav: Navigator = navigator,
  hostname: string = window.location.hostname,
): boolean {
  if (!isProduction || !("serviceWorker" in nav) || LOCAL_HOSTS.has(hostname)) return false;
  window.addEventListener("load", () => {
    nav.serviceWorker.register("/sw.js").catch(() => {
      // Not critical (e.g. private browsing); the app still works online.
    });
  });
  return true;
}
