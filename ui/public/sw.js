// Service worker mínimo: lo pide Chrome para ofrecer «Instalar» el IDE como app. No guarda nada en caché:
// el IDE es local y siempre en vivo (una versión vieja de la UI sería peor que nada).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
