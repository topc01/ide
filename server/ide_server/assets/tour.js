// server/ide_server/assets/tour.js
// Recorrido de una sesión (`ide tour`): abre un Chrome con la sesión local compartida, va paso a paso por las
// pantallas que preparó la sesión y muestra un recuadro con qué mirar. Lo que el usuario escribe se junta y, al
// terminar (o al cerrar la ventana), se le manda a la sesión de una vez. Lo lanza el server del IDE:
//   node tour.js <config.json>   (config: {steps, sid, ide, token, cookies, login, title})
const fs = require("fs");
const { chromium } = require("playwright-core");

const cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
fs.unlinkSync(process.argv[2]);          // lleva el token: no queda en disco
const steps = cfg.steps;
let idx = 0;
const notes = [];                         // {step, text}
let finished = false;

async function report(reason) {
  if (finished) return;
  finished = true;
  try {
    await fetch(`${cfg.ide}/api/tour/${encodeURIComponent(cfg.sid)}/done`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: cfg.token, notes, reason, seen: idx + 1, total: steps.length }),
    });
  } catch (e) { console.error("no pude avisarle al IDE:", e.message); }
}

const WIDGET = (state) => `(() => {
  if (window.top !== window) return;
  const S = ${JSON.stringify(state)};
  const mount = () => {
    if (document.getElementById("__ide_tour")) return;
    const box = document.createElement("div");
    box.id = "__ide_tour";
    box.attachShadow({ mode: "open" }).innerHTML = \`
      <style>
        .w{position:fixed;right:16px;bottom:16px;z-index:2147483647;width:340px;font:13px/1.4 -apple-system,system-ui,sans-serif;
           background:#1c1917;color:#f5f5f4;border:1px solid #f59e0b;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.4);padding:12px}
        .h{display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#fbbf24;margin-bottom:6px}
        .t{white-space:pre-wrap;margin-bottom:10px}
        textarea{width:100%;box-sizing:border-box;min-height:52px;background:#0c0a09;color:#f5f5f4;border:1px solid #57534e;border-radius:6px;padding:6px;font:inherit;resize:vertical}
        .b{display:flex;gap:6px;margin-top:8px}
        button{flex:1;background:#292524;color:#f5f5f4;border:1px solid #57534e;border-radius:6px;padding:5px;cursor:pointer;font:inherit}
        button:hover{border-color:#f59e0b} button:disabled{opacity:.4;cursor:default}
        .end{border-color:#f59e0b;color:#fbbf24}
        .n{font-size:11px;color:#a8a29e;margin-top:6px}
        .min{flex:0;padding:0 6px;border:none;background:none;color:#a8a29e}
      </style>
      <div class="w">
        <div class="h"><span class="hd"></span><button class="min" title="Minimizar">–</button></div>
        <div class="body">
          <div class="t"></div>
          <textarea placeholder="Comentario sobre esta pantalla (Enter lo guarda; le llegan todos juntos al terminar)"></textarea>
          <div class="b"><button class="prev">◀ Anterior</button><button class="next">Siguiente ▶</button></div>
          <div class="b"><button class="end">Terminar y mandar comentarios</button></div>
          <div class="n"></div>
        </div>
      </div>\`;
    const r = box.shadowRoot;
    r.querySelector(".t").textContent = S.text;
    r.querySelector(".hd").textContent = "Recorrido · " + S.title + " · paso " + (S.i + 1) + " de " + S.n;
    const note = () => r.querySelector(".n").textContent = S.count ? S.count + " comentario(s) guardado(s)" : "";
    note();
    r.querySelector(".prev").disabled = S.i === 0;
    r.querySelector(".next").disabled = S.i >= S.n - 1;
    const ta = r.querySelector("textarea");
    const save = async () => { const v = ta.value.trim(); if (!v) return; ta.value = ""; S.count = await window.__ideTour({ op: "note", text: v }); note(); };
    ta.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } });
    r.querySelector(".prev").onclick = async () => { await save(); window.__ideTour({ op: "go", d: -1 }); };
    r.querySelector(".next").onclick = async () => { await save(); window.__ideTour({ op: "go", d: 1 }); };
    r.querySelector(".end").onclick = async () => { await save(); window.__ideTour({ op: "end" }); };
    r.querySelector(".min").onclick = () => { const b = r.querySelector(".body"); b.style.display = b.style.display === "none" ? "" : "none"; };
    document.documentElement.appendChild(box);
    if (S.selector) {
      const tryMark = (k) => {
        const el = document.querySelector(S.selector);
        if (el) { el.scrollIntoView({ block: "center" }); el.style.outline = "3px solid #f59e0b"; el.style.outlineOffset = "3px"; }
        else if (k < 20) setTimeout(() => tryMark(k + 1), 500);
      };
      tryMark(0);
    }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
  setInterval(mount, 1500);   // las SPA rehacen el body: el recuadro vuelve
})();`;

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: false, args: ["--start-maximized"] });
  const ctx = await browser.newContext({ storageState: cfg.cookies, viewport: null });
  if (cfg.login) await ctx.addInitScript({ path: cfg.login });   // la sesión local compartida (localStorage por puerto)
  const page = await ctx.newPage();
  let widget = null;
  const show = async () => {
    const s = steps[idx];
    widget = WIDGET({ i: idx, n: steps.length, text: s.text, selector: s.selector || null, title: cfg.title, count: notes.length });
    await page.goto(s.url, { waitUntil: "domcontentloaded" }).catch(() => {});
    await page.evaluate(widget).catch(() => {});
  };
  // en cada navegación dentro del mismo paso (el usuario hace click), el recuadro vuelve
  page.on("domcontentloaded", () => { if (widget) page.evaluate(widget).catch(() => {}); });
  await ctx.exposeBinding("__ideTour", async (_src, msg) => {
    if (msg.op === "note") { notes.push({ step: idx + 1, url: page.url(), text: String(msg.text).slice(0, 2000) }); return notes.length; }
    if (msg.op === "go") { idx = Math.max(0, Math.min(steps.length - 1, idx + msg.d)); setTimeout(show, 0); return idx; }
    if (msg.op === "end") { await report("end"); setTimeout(() => browser.close().catch(() => {}), 300); }
    return null;
  });
  browser.on("disconnected", async () => { await report("closed"); process.exit(0); });
  await page.bringToFront();
  await show();
})().catch(async (e) => { console.error(e); await report("error: " + e.message); process.exit(1); });
