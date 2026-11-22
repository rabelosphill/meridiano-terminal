// Grava um vídeo de demonstração do Meridiano: dirige o Chrome (headless) pelo protocolo DevTools,
// captura os quadros com o horário real e grava frames/ + index.json. O encode em MP4 é feito por encode.swift.
// Uso: node scripts/demo/record.mjs <pasta-de-saída>   (servidor do Meridiano rodando em 127.0.0.1:8000)
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve(process.argv[2] || "demo-out");
const APP = "http://127.0.0.1:8000/";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333, W = 1920, H = 1080;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

fs.rmSync(path.join(OUT, "frames"), { recursive: true, force: true });
fs.rmSync(path.join(OUT, "chrome-profile"), { recursive: true, force: true });   // sem estado de gravações anteriores
fs.mkdirSync(path.join(OUT, "frames"), { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${path.join(OUT, "chrome-profile")}`,
  `--window-size=${W},${H}`, "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--force-device-scale-factor=1",
  "--force-color-profile=srgb", "about:blank"], { stdio: "ignore" });

let targets;
for (let i = 0; i < 60 && !targets; i++) { try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); } catch { await sleep(250); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let seq = 0; const pend = new Map(); const frames = [];
let recording = false;
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); return; }
  if (m.method === "Page.screencastFrame") {
    const { data, metadata, sessionId } = m.params;
    send("Page.screencastFrameAck", { sessionId }).catch(() => {});
    if (!recording) return;
    const f = `${String(frames.length).padStart(5, "0")}.jpg`;
    fs.writeFileSync(path.join(OUT, "frames", f), Buffer.from(data, "base64"));
    frames.push({ f, t: metadata.timestamp });
  }
};
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pend.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const js = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;

// ---------- primitivas ----------
let mx = W / 2, my = H / 2;
async function move(x, y, ms = 600) {
  const n = Math.max(1, Math.round(ms / 16)), x0 = mx, y0 = my;
  for (let i = 1; i <= n; i++) {
    const k = i / n, e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    mx = x0 + (x - x0) * e; my = y0 + (y - y0) * e;
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: mx, y: my });
    await sleep(16);
  }
}
async function click(x, y, ms) {
  await move(x, y, ms);
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await sleep(60);
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}
const KEYS = { Enter: 13, ArrowDown: 40, ArrowUp: 38, ArrowRight: 39, ArrowLeft: 37, Escape: 27, Tab: 9 };
async function key(k, times = 1, gap = 160) {
  for (let i = 0; i < times; i++) {
    const code = KEYS[k];
    const p = code ? { key: k, code: k, windowsVirtualKeyCode: code, nativeVirtualKeyCode: code } : { key: k, code: "Key" + k.toUpperCase(), text: k, windowsVirtualKeyCode: k.toUpperCase().charCodeAt(0) };
    await send("Input.dispatchKeyEvent", { type: code ? "rawKeyDown" : "keyDown", ...p, ...(k === "Enter" ? { text: "\r" } : {}) });
    await send("Input.dispatchKeyEvent", { type: "keyUp", ...p });
    await sleep(gap);
  }
}
async function type(text, gap = 65) { for (const ch of text) { await send("Input.insertText", { text: ch }); await sleep(gap + Math.random() * 40); } }
/** centro de um elemento: seletor CSS + (opcional) trecho do texto */
async function at(sel, txt = "") {
  const r = await js(`(() => { const els=[...document.querySelectorAll(${JSON.stringify(sel)})].filter(e=>e.offsetParent!==null);
    const e = ${JSON.stringify(txt)} ? els.find(x=>x.textContent.trim().startsWith(${JSON.stringify(txt)})) : els[0];
    if(!e) return null; e.scrollIntoView({block:'nearest'}); const b=e.getBoundingClientRect(); return {x:b.x+b.width/2,y:b.y+b.height/2,w:b.width,h:b.height,l:b.x,t:b.y}; })()`);
  if (!r) throw new Error(`elemento não encontrado: ${sel} ${txt}`);
  return r;
}
async function clickOn(sel, txt, ms) { const r = await at(sel, txt); await click(r.x, r.y, ms); return r; }
async function command(text) { await clickOn(".cmd input", "", 500); await js(`document.querySelector('.cmd input').select()`); await type(text); await sleep(350); await key("Enter"); }
const caption = (n, title, sub = "") => js(`window.__demo.cap(${JSON.stringify(n)}, ${JSON.stringify(title)}, ${JSON.stringify(sub)})`);
const card = (title, sub, kicker) => js(`window.__demo.card(${JSON.stringify(title)}, ${JSON.stringify(sub)}, ${JSON.stringify(kicker || "")})`);
const uncard = () => js(`window.__demo.uncard()`);

const OVERLAY = `(() => {
  if (window.__demo) return;
  const css = document.createElement('style');
  css.textContent = \`
  #demo-cur{position:fixed;z-index:2147483647;width:22px;height:22px;pointer-events:none;left:0;top:0;transform:translate(-3px,-2px);transition:none}
  #demo-cur svg{filter:drop-shadow(0 1px 2px rgba(0,0,0,.6))}
  #demo-ring{position:fixed;z-index:2147483646;width:34px;height:34px;border-radius:50%;border:2px solid #e8b04a;pointer-events:none;opacity:0;transform:translate(-50%,-50%) scale(.4);transition:opacity .35s, transform .35s}
  #demo-cap{position:fixed;z-index:2147483645;left:50%;bottom:64px;transform:translate(-50%,16px);opacity:0;transition:opacity .45s, transform .45s;pointer-events:none;
    background:rgba(10,13,16,.92);border:1px solid rgba(232,176,74,.55);border-left:5px solid #e8b04a;border-radius:6px;padding:14px 26px 14px 20px;
    font-family:'Inter','Helvetica Neue',Arial,sans-serif;color:#f2f2f2;box-shadow:0 12px 40px rgba(0,0,0,.55);min-width:520px;max-width:1200px}
  #demo-cap.on{opacity:1;transform:translate(-50%,0)}
  #demo-cap .n{font:700 13px ui-monospace,Menlo,monospace;color:#e8b04a;letter-spacing:.12em;margin-bottom:4px}
  #demo-cap .t{font-weight:700;font-size:28px;letter-spacing:-.01em}
  #demo-cap .s{font-size:17px;color:#b9c0c7;margin-top:4px}
  #demo-card{position:fixed;inset:0;z-index:2147483644;background:radial-gradient(ellipse at 50% 40%, #16202a 0%, #07090c 70%);display:flex;flex-direction:column;
    align-items:center;justify-content:center;opacity:0;transition:opacity .6s;pointer-events:none;font-family:'Inter','Helvetica Neue',Arial,sans-serif;color:#f4f4f4;text-align:center}
  #demo-card.on{opacity:1}
  #demo-card .k{font:600 18px ui-monospace,Menlo,monospace;color:#46d3c3;letter-spacing:.3em;margin-bottom:26px}
  #demo-card .t{font-size:96px;font-weight:800;letter-spacing:.06em}
  #demo-card .t b{color:#e8b04a}
  #demo-card .s{font-size:26px;color:#aeb6be;margin-top:22px;max-width:1200px;line-height:1.45}
  #demo-card .bar{width:120px;height:4px;background:#e8b04a;margin-top:34px;border-radius:2px}\`;
  document.head.appendChild(css);
  const cur = document.createElement('div'); cur.id='demo-cur';
  cur.innerHTML='<svg width="22" height="22" viewBox="0 0 22 22"><path d="M2 1 L2 18 L6.5 13.8 L9.6 20.5 L12.6 19.2 L9.5 12.6 L15.5 12.6 Z" fill="#fff" stroke="#111" stroke-width="1.3" stroke-linejoin="round"/></svg>';
  const ring = document.createElement('div'); ring.id='demo-ring';
  const cap = document.createElement('div'); cap.id='demo-cap';
  const card = document.createElement('div'); card.id='demo-card';
  document.body.append(card, cap, ring, cur);
  addEventListener('mousemove', e => { cur.style.left=e.clientX+'px'; cur.style.top=e.clientY+'px'; }, true);
  addEventListener('mousedown', e => { ring.style.left=e.clientX+'px'; ring.style.top=e.clientY+'px'; ring.style.transition='none'; ring.style.opacity='1'; ring.style.transform='translate(-50%,-50%) scale(.4)';
    requestAnimationFrame(()=>{ ring.style.transition='opacity .45s, transform .45s'; ring.style.opacity='0'; ring.style.transform='translate(-50%,-50%) scale(1.5)'; }); }, true);
  window.__demo = {
    cap(n,t,s){ cap.classList.remove('on'); setTimeout(()=>{ cap.innerHTML=(n?'<div class="n">'+n+'</div>':'')+'<div class="t">'+t+'</div>'+(s?'<div class="s">'+s+'</div>':''); cap.classList.add('on'); }, cap.innerHTML?300:0); },
    hide(){ cap.classList.remove('on'); },
    card(t,s,k){ card.innerHTML=(k?'<div class="k">'+k+'</div>':'')+'<div class="t">'+t+'</div><div class="s">'+s+'</div><div class="bar"></div>'; card.classList.add('on'); cap.classList.remove('on'); },
    uncard(){ card.classList.remove('on'); },
  };
})()`;

// ---------- roteiro ----------
await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
await send("Page.addScriptToEvaluateOnNewDocument", { source: `localStorage.setItem('meridiano.user','ana');` });
await send("Page.navigate", { url: APP + "#cmd=MARKETS+BR+US" });
await sleep(3500);
await js(OVERLAY);
await card("MERI<b>DIANO</b>", "Terminal de mercado Brasil–EUA", "TERMINAL PESSOAL DE MERCADO");
await send("Page.startScreencast", { format: "jpeg", quality: 88, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
await sleep(400);
recording = true;
const t0 = Date.now();
const mark = (s) => console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s  ${s}`);

await sleep(3800);
await card("MERI<b>DIANO</b>", "Dados oficiais da B3, CVM, SEC e Banco Central — cada número com a sua fonte", "TERMINAL PESSOAL DE MERCADO");
await sleep(3000);
await uncard(); await sleep(700);

// 1 · Monitor
mark("markets");
await caption("01 · MONITOR", "Brasil e EUA na mesma tela", "Ações, ADRs, índices, câmbio, juros, commodities e macro");
await move(700, 420, 900); await sleep(1200); await move(1100, 560, 900); await sleep(2200);

// 2 · Busca por nome
mark("busca");
await caption("02 · BUSCA", "680 empresas da B3 pelo nome ou pelo ticker", "Barra de comando com sugestões instantâneas");
await clickOn(".cmd input", "", 700); await js(`document.querySelector('.cmd input').select()`);
await type("magazine", 110); await sleep(1600);
await clickOn(".sugg .it", "MGLU3", 900); await sleep(2600);
await move(900, 500, 800); await sleep(1500);

// 3 · Gráfico
mark("grafico");
await caption("03 · GRÁFICO", "Análise técnica com eventos no candle certo", "Médias, RSI, MACD, Bollinger, VWAP · resultados e comunicados na 1ª sessão negociável");
await clickOn(".hdrnav button", "Gráfico", 800); await sleep(2600);
await clickOn("button.btn", "Estudos", 700); await sleep(900);
await clickOn("button.chip", "+ RSI", 700); await sleep(1400);
await clickOn("button", "Fechar", 600); await sleep(900);
const cv = await at("canvas");
await move(cv.l + cv.w * 0.18, cv.t + cv.h * 0.35, 700);
await move(cv.l + cv.w * 0.86, cv.t + cv.h * 0.42, 4200);
await sleep(900);

// 4 · Demonstrações com fonte
mark("fin");
await caption("04 · DEMONSTRAÇÕES", "DRE, balanço e caixa direto da CVM e da SEC", "Trimestral, anual ou 12 meses — sem planilha, sem copiar e colar");
await command("PETR4 B3 FIN Q"); await sleep(2600);
await js(`document.querySelector('.grid').focus()`);
await key("ArrowDown", 2, 380); await key("ArrowRight", 1, 380); await sleep(400);
await caption("04 · DEMONSTRAÇÕES", "Cada número com a sua origem", "Enter mostra documento, data de divulgação, conta e versões · S abre o arquivo original");
await key("Enter"); await sleep(2800);
await key("s"); await sleep(3200);
await key("Escape"); await sleep(1200);

// 5 · Valuation
mark("value");
await caption("05 · VALUATION", "Múltiplos e DCF auditável", "P/L, EV/EBIT, P/VP com o fechamento oficial da B3 + fluxo de caixa descontado");
await command("WEGE3 B3 VALUE"); await sleep(2600);
await move(800, 520, 900); await js(`document.querySelector('.view')?.scrollBy({top:420,behavior:'smooth'})`); await sleep(2600);

// 6 · Comparação
mark("compare");
await caption("06 · COMPARAÇÃO", "Empresas lado a lado, Brasil e EUA", "Moeda e período sempre explícitos");
await command("COMPARE PETR4:B3 VALE3:B3 ITUB4:B3"); await sleep(4200);

// 7 · Notícias
mark("news");
await caption("07 · NOTÍCIAS", "Fatos relevantes, 8-K, Fed e Copom em tempo de pregão", "Cada manchete ligada aos ativos e à sessão em que pôde ser negociada");
await command("NEWS WORLD"); await sleep(2200);
{ const r = await js(`(() => { const e=[...document.querySelectorAll('table.tbl tr[tabindex]')].find(x=>{const b=x.getBoundingClientRect(); return b.x>300 && b.x<900 && b.y>150;});
     const b=e.getBoundingClientRect(); return {x:b.x+260,y:b.y+b.height/2}; })()`);
  await click(r.x, r.y, 800); await sleep(3000); }

// 8 · Rastreador
mark("scan");
await caption("08 · RASTREADOR", "Filtros sobre todo o mercado, com o motivo de cada escolha", "Liquidez, tendência, força relativa — e quem ficou de fora e por quê");
await command("SCAN BR"); await sleep(800);
await move(700, 600, 900);
for (let i = 0; i < 60 && !(await js(`[...document.querySelectorAll('button.btn.pri')].some(b=>b.textContent.trim()==='Rodar')`)); i++) await sleep(250);
await sleep(1200); await js(`document.querySelector('.view')?.scrollBy({top:260,behavior:'smooth'})`); await sleep(3000);

// 9 · Macro
mark("macro");
await caption("09 · MACRO", "Selic, IPCA, câmbio e juros americanos", "Séries do Banco Central e do FRED com data de divulgação");
await command("MACRO BR SELIC"); await sleep(3800);

// 10 · EUA
mark("eua");
await caption("10 · ESTADOS UNIDOS", "Ações americanas com 10-K/10-Q da SEC", "Mesma análise, mesma rastreabilidade");
await command("AAPL NASDAQ CHART 1D 1Y"); await sleep(2200);
{ const c = await at("canvas"); await move(c.l + c.w * 0.3, c.t + c.h * 0.45, 700); await move(c.l + c.w * 0.92, c.t + c.h * 0.3, 2600); await sleep(800); }

mark("fim");
await js(`window.__demo.hide()`);
await card("MERI<b>DIANO</b>", "Mercado, empresas e análise em um só lugar — feito para acompanhar o mercado todos os dias", "PROJETO PESSOAL");
await sleep(4500);

recording = false;
await send("Page.stopScreencast");
fs.writeFileSync(path.join(OUT, "index.json"), JSON.stringify(frames));
console.log(`quadros: ${frames.length} · duração ${(frames.at(-1).t - frames[0].t).toFixed(1)} s`);
ws.close(); chrome.kill();
process.exit(0);
