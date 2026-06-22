/* Service Worker — SERCOP Monitor Previfuego */

const CACHE   = 'previfuego-v1';
const API_URL = 'https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds';
const VISTOS_KEY = 'nco_vistos';

// ── Instalación ───────────────────────────────────────────────────────────────
self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c =>
      Promise.allSettled([
        c.add('/SERCOP/index.html'),
        c.add('/SERCOP/manifest.json'),
        c.add('/SERCOP/sw.js'),
      ])
    )
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(clients.claim());
});

// ── Cache-first para recursos estáticos ───────────────────────────────────────
self.addEventListener('fetch', e => {
  if (!e.request.url.startsWith('http')) return;
  if (e.request.url.includes('datosabiertos.compraspublicas') ||
      e.request.url.includes('nco-guayas.json')) return; // no cachear API
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});

// ── Periodic Background Sync (Android Chrome) ─────────────────────────────────
self.addEventListener('periodicsync', e => {
  if (e.tag === 'check-nco') {
    e.waitUntil(verificarNuevosNCO());
  }
});

// ── Mensaje desde la página: verificar ahora ─────────────────────────────────
self.addEventListener('message', e => {
  if (e.data?.type === 'CHECK_NOW') {
    verificarNuevosNCO();
  }
  if (e.data?.type === 'MARCAR_VISTOS') {
    guardarVistos(e.data.ids);
  }
});

// ── Push desde servidor (futuro) ─────────────────────────────────────────────
self.addEventListener('push', e => {
  let data = {};
  try { data = e.data?.json() || {}; } catch {};
  e.waitUntil(
    self.registration.showNotification(data.title || '🔥 Nuevo proceso SERCOP', {
      body: data.body || 'Hay un nuevo proceso de extintores en Guayas',
      icon:  '/SERCOP/icons/icon-192.png',
      badge: '/SERCOP/icons/icon-192.png',
      tag:   data.tag || 'nco-nuevo',
      data:  { url: data.url || '/SERCOP/' },
      vibrate: [200, 100, 200],
      requireInteraction: true,
    })
  );
});

// ── Click en notificación → abre la app ───────────────────────────────────────
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || '/SERCOP/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
      const existing = cs.find(c => c.url.includes('/SERCOP/'));
      if (existing) { existing.focus(); existing.navigate(url); }
      else clients.openWindow(url);
    })
  );
});

// ── Lógica de verificación ────────────────────────────────────────────────────

async function getVistos() {
  try {
    const db = await openDB();
    return (await dbGet(db, VISTOS_KEY)) || [];
  } catch { return []; }
}

async function guardarVistos(ids) {
  try {
    const db = await openDB();
    const actuales = (await dbGet(db, VISTOS_KEY)) || [];
    const merged = [...new Set([...actuales, ...ids])];
    await dbSet(db, VISTOS_KEY, merged);
  } catch {}
}

async function verificarNuevosNCO() {
  const keywords = ['extintores', 'recarga extintores', 'proteccion incendios'];
  const anio = new Date().getFullYear();
  const vistos = await getVistos();
  const nuevos = [];

  for (const kw of keywords) {
    try {
      const url = `${API_URL}?year=${anio}&search=${encodeURIComponent(kw)}&page=1`;
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) continue;
      const data = await res.json();
      const items = (data.data || []).filter(p => {
        const r = (p.region || '').toUpperCase();
        const l = (p.locality || '').toUpperCase();
        return r.includes('GUAYAS') || l.includes('GUAYAS') || l.includes('GUAYAQUIL');
      });
      for (const p of items) {
        const id = p.ocid || String(p.id);
        if (!vistos.includes(id) && !nuevos.find(x => (x.ocid || x.id) === (p.ocid || p.id))) {
          nuevos.push(p);
        }
      }
    } catch {}
  }

  if (nuevos.length === 0) return;

  // Guardar como vistos
  await guardarVistos(nuevos.map(p => p.ocid || String(p.id)));

  // Enviar notificación por cada uno (máx 3 para no saturar)
  const mostrar = nuevos.slice(0, 3);
  for (const p of mostrar) {
    const monto = p.amount ? ` | $${parseFloat(p.amount).toLocaleString('es-EC')}` : '';
    await self.registration.showNotification('🔥 Nuevo proceso en Guayas — SERCOP', {
      body:   `${p.description || p.title || p.ocid}\n${p.buyer || ''}${monto}`,
      icon:   '/SERCOP/icons/icon-192.png',
      badge:  '/SERCOP/icons/icon-192.png',
      tag:    p.ocid || String(p.id),
      data:   {
        url: `https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/ocds/${encodeURIComponent(p.ocid || '')}`,
      },
      vibrate: [200, 100, 200],
      requireInteraction: true,
    });
  }

  if (nuevos.length > 3) {
    await self.registration.showNotification(
      `🔥 +${nuevos.length - 3} proceso(s) más en Guayas`,
      { body: 'Abre la app para ver todos', icon: '/SERCOP/icons/icon-192.png', tag: 'nco-extra' }
    );
  }

  // Notificar a las pestañas abiertas
  const allClients = await clients.matchAll({ includeUncontrolled: true });
  allClients.forEach(c => c.postMessage({ type: 'NUEVOS_NCO', count: nuevos.length }));
}

// ── IndexedDB mínimo para persistir los IDs vistos ───────────────────────────

function openDB() {
  return new Promise((res, rej) => {
    const req = indexedDB.open('previfuego', 1);
    req.onupgradeneeded = e => e.target.result.createObjectStore('kv');
    req.onsuccess = e => res(e.target.result);
    req.onerror   = e => rej(e.target.error);
  });
}

function dbGet(db, key) {
  return new Promise((res, rej) => {
    const tx = db.transaction('kv', 'readonly');
    const req = tx.objectStore('kv').get(key);
    req.onsuccess = () => res(req.result);
    req.onerror   = e => rej(e.target.error);
  });
}

function dbSet(db, key, val) {
  return new Promise((res, rej) => {
    const tx = db.transaction('kv', 'readwrite');
    const req = tx.objectStore('kv').put(val, key);
    req.onsuccess = () => res();
    req.onerror   = e => rej(e.target.error);
  });
}