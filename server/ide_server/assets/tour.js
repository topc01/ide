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
// solo el recuadro conoce esta clave (va dentro de su función, en un shadow DOM cerrado): el código de la página que
// se recorre puede ver la función __ideTour, pero no inventar comentarios ni terminar el recorrido
const NONCE = require("crypto").randomBytes(18).toString("hex");
let idx = 0;
const notes = [];                         // {step, text}
let finished = false;
let theme = cfg.theme === "light" ? "light" : "dark";
const readPos = () => { try { const p = JSON.parse(fs.readFileSync(cfg.pos_file, "utf8")); return Number.isFinite(p.x) && Number.isFinite(p.y) ? { x: p.x, y: p.y } : null; } catch { return null; } };
let pos = cfg.pos_file ? readPos() : null;   // donde el usuario dejó el recuadro (vale para los siguientes recorridos)
// sigue el tema del IDE mientras el recorrido está abierto
setInterval(async () => {
  try { const r = await fetch(`${cfg.ide}/api/ui/theme`); const j = await r.json(); if (j.theme === "light" || j.theme === "dark") theme = j.theme; } catch {}
}, 2000).unref();

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
    if (document.getElementById("__ide_tour")) return;   // (ya está: su intervalo de tema sigue corriendo)
    const box = document.createElement("div");
    box.id = "__ide_tour";
    const root = box.attachShadow({ mode: "closed" });
    root.innerHTML = \`
      <style>
        .w{--bg:#1c1917;--fg:#f5f5f4;--ac:#f59e0b;--ac2:#fbbf24;--in:#0c0a09;--bd:#57534e;--btn:#292524;--mu:#a8a29e;--sh:rgba(0,0,0,.4);
           position:fixed;z-index:2147483647;width:340px;font:13px/1.4 -apple-system,system-ui,sans-serif;
           background:var(--bg);color:var(--fg);border:1px solid var(--ac);border-radius:10px;box-shadow:0 8px 30px var(--sh);padding:12px}
        .w.light{--bg:#fffbeb;--fg:#1c1917;--ac:#d97706;--ac2:#b45309;--in:#ffffff;--bd:#d6d3d1;--btn:#f5f5f4;--mu:#78716c;--sh:rgba(0,0,0,.18)}
        .h{display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--ac2);margin:-12px -12px 6px;padding:8px 12px 4px;cursor:move;user-select:none}
        .t{white-space:pre-wrap;margin-bottom:10px}
        textarea{width:100%;box-sizing:border-box;min-height:52px;background:var(--in);color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:6px;font:inherit;resize:vertical}
        .b{display:flex;gap:6px;margin-top:8px}
        button{flex:1;background:var(--btn);color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:5px;cursor:pointer;font:inherit}
        button:hover{border-color:var(--ac)} button:disabled{opacity:.4;cursor:default}
        .end{border-color:var(--ac);color:var(--ac2)}
        .n{font-size:11px;color:var(--mu);margin-top:6px}
        .min{flex:0;padding:0 6px;border:none;background:none;color:var(--mu)}
      </style>
      <div class="w">
        <div class="h" title="Arrastra para moverlo"><span class="hd"></span><button class="min" title="Minimizar">–</button></div>
        <div class="body">
          <div class="t"></div>
          <textarea placeholder="Comentario sobre esta pantalla (Enter lo guarda; le llegan todos juntos al terminar)"></textarea>
          <div class="b"><button class="prev">◀ Anterior</button><button class="next">Siguiente ▶</button></div>
          <div class="b"><button class="end">Terminar y mandar comentarios</button></div>
          <div class="n"></div>
        </div>
      </div>\`;
    const r = root;
    r.querySelector(".t").textContent = S.text;
    r.querySelector(".hd").textContent = "Recorrido · " + S.title + " · paso " + (S.i + 1) + " de " + S.n;
    const note = () => r.querySelector(".n").textContent = S.count ? S.count + " comentario(s) guardado(s)" : "";
    note();
    r.querySelector(".prev").disabled = S.i === 0;
    r.querySelector(".next").disabled = S.i >= S.n - 1;
    const ta = r.querySelector("textarea");
    const save = async () => { const v = ta.value.trim(); if (!v) return; ta.value = ""; S.count = await window.__ideTour({ op: "note", text: v, k: S.k }); note(); };
    ta.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); } });
    r.querySelector(".prev").onclick = async () => { await save(); window.__ideTour({ op: "go", d: -1, k: S.k }); };
    r.querySelector(".next").onclick = async () => { await save(); window.__ideTour({ op: "go", d: 1, k: S.k }); };
    r.querySelector(".end").onclick = async () => { await save(); window.__ideTour({ op: "end", k: S.k }); };
    r.querySelector(".min").onclick = () => { const b = r.querySelector(".body"); b.style.display = b.style.display === "none" ? "" : "none"; };
    const w = r.querySelector(".w");
    const setTheme = (t) => w.classList.toggle("light", t === "light");
    setTheme(S.theme);
    // posición: la que dejó el usuario (esquina sup. izq.), dentro de la ventana; si no hay, abajo a la derecha
    const place = (x, y) => {
      const mx = Math.max(0, window.innerWidth - w.offsetWidth), my = Math.max(0, window.innerHeight - w.offsetHeight);
      w.style.left = Math.min(Math.max(0, x), mx) + "px"; w.style.top = Math.min(Math.max(0, y), my) + "px";
      w.style.right = "auto"; w.style.bottom = "auto";
    };
    const h = r.querySelector(".h");
    h.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button")) return;
      e.preventDefault();
      const rc = w.getBoundingClientRect(), dx = e.clientX - rc.left, dy = e.clientY - rc.top;
      h.setPointerCapture(e.pointerId);
      const move = (ev) => place(ev.clientX - dx, ev.clientY - dy);
      const up = () => {
        h.removeEventListener("pointermove", move); h.removeEventListener("pointerup", up);
        const b = w.getBoundingClientRect();
        S.pos = { x: Math.round(b.left), y: Math.round(b.top) };
        window.__ideTour({ op: "pos", x: S.pos.x, y: S.pos.y, k: S.k });
      };
      h.addEventListener("pointermove", move); h.addEventListener("pointerup", up);
    });
    document.documentElement.appendChild(box);
    if (S.pos) place(S.pos.x, S.pos.y); else { w.style.right = "16px"; w.style.bottom = "16px"; }
    window.addEventListener("resize", () => { if (S.pos) place(S.pos.x, S.pos.y); });
    // el tema del IDE puede cambiar con el recorrido abierto
    setInterval(async () => { const t = await window.__ideTour({ op: "theme", k: S.k }).catch(() => null); if (t) setTheme(t); }, 2000);
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
  let shown = false;
  // se arma en el momento: posición, tema y comentarios al día (también al navegar dentro del paso)
  const widget = () => { const s = steps[idx]; return WIDGET({ k: NONCE, i: idx, n: steps.length, text: s.text, selector: s.selector || null,
    title: cfg.title, count: notes.length, theme, pos }); };
  const show = async () => {
    shown = true;
    await page.goto(steps[idx].url, { waitUntil: "domcontentloaded" }).catch(() => {});
    await page.evaluate(widget()).catch(() => {});
  };
  // en cada navegación dentro del mismo paso (el usuario hace click), el recuadro vuelve
  page.on("domcontentloaded", () => { if (shown) page.evaluate(widget()).catch(() => {}); });
  await ctx.exposeBinding("__ideTour", async (src, msg) => {
    if (!msg || msg.k !== NONCE || src.frame !== page.mainFrame()) return null;
    if (msg.op === "note") { notes.push({ step: idx + 1, url: page.url(), text: String(msg.text).slice(0, 2000) }); return notes.length; }
    if (msg.op === "go") { idx = Math.max(0, Math.min(steps.length - 1, idx + msg.d)); setTimeout(show, 0); return idx; }
    if (msg.op === "theme") return theme;
    if (msg.op === "pos") {
      const x = Math.round(Number(msg.x)), y = Math.round(Number(msg.y));
      if (Number.isFinite(x) && Number.isFinite(y)) {
        pos = { x, y };
        try { if (cfg.pos_file) fs.writeFileSync(cfg.pos_file, JSON.stringify(pos)); } catch (e) { console.error("no pude guardar la posición:", e.message); }
      }
      return null;
    }
    if (msg.op === "end") { await report("end"); setTimeout(() => browser.close().catch(() => {}), 300); }
    return null;
  });
  browser.on("disconnected", async () => { await report("closed"); process.exit(0); });
  await page.bringToFront();
  await show();
})().catch(async (e) => { console.error(e); await report("error: " + e.message); process.exit(1); });
