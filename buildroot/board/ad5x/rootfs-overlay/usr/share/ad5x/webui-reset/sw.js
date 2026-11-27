// Kiln OS: this printer now serves another web interface (Fluidd or
// Mainsail; docs/web-interface.md). nginx sends this worker in place of
// the old interface's service worker: it takes over at once, deletes the
// pages that worker cached (Cache Storage only: settings in the browser's
// local storage stay), unregisters itself and reloads the tabs, which
// then get the new interface from the printer. Nothing is cached here.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.clients.claim();
    await self.registration.unregister();
    // Only when an old interface was cached: a page that registers this
    // worker with nothing cached isn't reloaded (no reload loop)
    if (keys.length) {
      const tabs = await self.clients.matchAll({ type: "window" });
      for (const tab of tabs) tab.navigate(tab.url);
    }
  })());
});
