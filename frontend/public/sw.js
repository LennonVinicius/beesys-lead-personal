/* BeeSys Lead Search — conservative PWA cache.
 * Navigation is always network-first and never served stale while online.
 * Only versioned /assets/* bundles use cache-first. This avoids the old Vite
 * stale-shell blank-screen problem while keeping the current app usable when
 * connectivity drops in Modo Rua.
 */
const VERSION='beesys-lead-pwa-v3'
const ASSETS=`${VERSION}-assets`
const OFFLINE=`${VERSION}-offline`

self.addEventListener('install',event=>{
  self.skipWaiting()
  event.waitUntil(caches.open(OFFLINE).then(cache=>cache.add(new Request('/',{cache:'reload'}))).catch(()=>{}))
})
self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{
    const keys=await caches.keys()
    await Promise.all(keys.filter(k=>k.startsWith('beesys-lead-')&&![ASSETS,OFFLINE].includes(k)).map(k=>caches.delete(k)))
    await self.clients.claim()
  })())
})
self.addEventListener('fetch',event=>{
  const req=event.request
  if(req.method!=='GET')return
  const url=new URL(req.url)
  if(url.origin!==self.location.origin)return
  if(url.pathname.startsWith('/assets/')){
    event.respondWith(caches.open(ASSETS).then(async cache=>{
      const hit=await cache.match(req)
      if(hit)return hit
      const response=await fetch(req)
      if(response.ok)cache.put(req,response.clone())
      return response
    }))
    return
  }
  if(req.mode==='navigate'){
    event.respondWith((async()=>{
      try{
        const response=await fetch(new Request(req,{cache:'no-store'}))
        if(response.ok){const cache=await caches.open(OFFLINE);await cache.put('/',response.clone())}
        return response
      }catch{
        const cached=await caches.open(OFFLINE).then(c=>c.match('/'))
        return cached||Response.error()
      }
    })())
  }
})
