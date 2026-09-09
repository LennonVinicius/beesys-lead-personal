/*
 * BeeSys Lead Search - Service Worker de desativação.
 *
 * A versão anterior fazia cache amplo do shell e dos bundles da Vite, o que
 * podia produzir tela branca após um novo deploy. Este worker existe apenas
 * para substituir instalações antigas, apagar os caches e se desregistrar.
 */
self.addEventListener('install', (event) => {
  self.skipWaiting()
  event.waitUntil(Promise.resolve())
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.filter((key) => key.startsWith('beesys-lead-')).map((key) => caches.delete(key)))
      await self.registration.unregister()
      const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const client of clients) client.navigate(client.url)
    })(),
  )
})
