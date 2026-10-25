importScripts('./feed-status.js');
const VERSION = 'radar-static-v11';
const ASSETS = ['./','./index.html','./styles.css','./feed-status.js','./app.js','./manifest.webmanifest','./assets/icon.svg'];
const isFeed = req => new URL(req.url).pathname.endsWith('/data/news.json');
self.addEventListener('install', event => event.waitUntil((async () => {
  await (await caches.open(VERSION)).addAll(ASSETS);
  await self.skipWaiting();
})()));
self.addEventListener('activate', event => event.waitUntil((async () => {
  const current = await caches.open(VERSION);
  const feedURL = new URL('./data/news.json', self.location.href).href;
  // Preserve the last valid feed across upgrades, without touching other apps' caches.
  for (const key of (await caches.keys()).reverse()) {
    if (key === VERSION || !key.startsWith('radar-static-')) continue;
    const previous = await (await caches.open(key)).match(feedURL);
    if (previous && !await current.match(feedURL)) {
      try { RadarFeed.validate(await previous.clone().json()); } catch { await caches.delete(key); continue; }
      try { await current.put(feedURL, previous); } catch { continue; } // Keep a valid backup when migration cannot write.
    }
    await caches.delete(key);
  }
  await self.clients.claim();
})()));
async function cachedFeed(req) {
  const keys = [VERSION, ...(await caches.keys()).reverse().filter(key => key !== VERSION && key.startsWith('radar-static-'))];
  for (const key of keys) {
    const saved = await (await caches.open(key)).match(req);
    if (!saved) continue;
    try {
      RadarFeed.validate(await saved.clone().json());
      const headers = new Headers(saved.headers);
      headers.set('X-Curiosity-Radar-Cache', 'fallback');
      return new Response(saved.body, {status: 200, headers});
    } catch { /* Never present a corrupt cache as valid news. */ }
  }
  return new Response('', {status: 503});
}

async function feedResponse(req) {
  let response;
  try { response = await fetch(req); } catch { return cachedFeed(req); }
  if (!response.ok) {
    const saved = await cachedFeed(req);
    return saved.ok ? saved : response;
  }
  try {
    RadarFeed.validate(await response.clone().json());
    await (await caches.open(VERSION)).put(req, response.clone());
  } catch { /* Return the network response for page validation; keep the good cache. */ }
  return response;
}
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  if (isFeed(req)) { event.respondWith(feedResponse(req)); return; }
  event.respondWith((async () => {
    let response;
    try { response = await fetch(req); }
    catch { return await (await caches.open(VERSION)).match(req) || await caches.match(req) || new Response('', {status: 503}); }
    if (response.ok) {
      try { await (await caches.open(VERSION)).put(req, response.clone()); }
      catch { /* Storage failure must not discard a successful network response. */ }
    }
    return response;
  })());
});
