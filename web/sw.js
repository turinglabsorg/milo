import {deviceCache} from '/static/cache.js';
const CACHE = 'milo-shell-v7';
const SHELL = ['/', '/static/style.css', '/static/app.js', '/static/cache.js', '/static/icon.svg', '/static/fonts/Geist.woff2'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if(url.origin===self.location.origin&&/^\/api\/messages\/[^/]+\/attachments\/\d+$/.test(url.pathname)&&event.request.method==='GET'){
    event.respondWith(fetch(event.request).then(response=>{
      if(response.ok)event.waitUntil(deviceCache.setAsset(url.pathname,response.clone()).catch(()=>{}));
      return response;
    }).catch(async()=>await deviceCache.getAsset(url.pathname)||Response.error()));
    return;
  }
  // API data is managed explicitly in the device's encrypted IndexedDB cache.
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/') || event.request.method !== 'GET') return;
  // The installed app must start from the device even if a remote host stalls.
  event.respondWith(caches.match(event.request).then(cached=>{
    const fresh=fetch(event.request).then(async response=>{
      if(response.status===401||response.status===404)await caches.delete(CACHE);
      return response;
    });
    if(cached){event.waitUntil(fresh.catch(()=>{}));return cached;}
    return fresh;
  }));
});
