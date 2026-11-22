// Prints das principais telas (PNG 1920x1080, sem legendas sobrepostas) para divulgação.
// Uso: node scripts/demo/shots.mjs <pasta-de-saída> <pasta-de-trabalho>
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve(process.argv[2] || "media/prints");
const WORK = path.resolve(process.argv[3] || "demo-out");
const APP = "http://127.0.0.1:8000/";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333, W = 1920, H = 1080;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
fs.mkdirSync(OUT, { recursive: true });
fs.rmSync(path.join(WORK, "chrome-profile-shots"), { recursive: true, force: true });
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${path.join(WORK, "chrome-profile-shots")}`,
  `--window-size=${W},${H}`, "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--force-device-scale-factor=1",
  "--force-color-profile=srgb", "about:blank"], { stdio: "ignore" });
let targets;
for (let i = 0; i < 60 && !targets; i++) { try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); } catch { await sleep(250); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let seq = 0; const pend = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)) { const p = pend.get(m.id); pend.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } };
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pend.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const js = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;
const run = (cmd) => js(`window.__meridianoRun(${JSON.stringify(cmd)})`);
const mouse = (x, y) => send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
async function key(k) {
  const codes = { Enter: 13, ArrowDown: 40, ArrowRight: 39, Escape: 27 };
  const p = codes[k] ? { key: k, code: k, windowsVirtualKeyCode: codes[k] } : { key: k, code: "Key" + k.toUpperCase(), text: k, windowsVirtualKeyCode: k.toUpperCase().charCodeAt(0) };
  await send("Input.dispatchKeyEvent", { type: codes[k] ? "rawKeyDown" : "keyDown", ...p, ...(k === "Enter" ? { text: "\r" } : {}) });
  await send("Input.dispatchKeyEvent", { type: "keyUp", ...p }); await sleep(250);
}
async function rect(expr) { return js(`(() => { const e=${expr}; if(!e) return null; const b=e.getBoundingClientRect(); return {x:b.x+b.width/2,y:b.y+b.height/2,l:b.x,t:b.y,w:b.width,h:b.height}; })()`); }
async function clickEl(expr) {
  const r = await rect(expr); if (!r) throw new Error("não encontrado: " + expr);
  await mouse(r.x, r.y);
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: r.x, y: r.y, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: r.x, y: r.y, button: "left", clickCount: 1 });
}
async function shot(name) {
  await sleep(400);
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT, name + ".png"), Buffer.from(data, "base64"));
  console.log("ok", name);
}

await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
await send("Page.addScriptToEvaluateOnNewDocument", { source: `localStorage.setItem('meridiano.user','ana');` });
await send("Page.navigate", { url: APP + "#cmd=MARKETS+BR+US" });
await sleep(4000);
await mouse(1900, 1070);
await shot("01-monitor-brasil-eua");

// busca com sugestões abertas
await clickEl(`document.querySelector('.cmd input')`);
await send("Input.insertText", { text: "magazine" }); await sleep(1200);
await shot("02-busca-por-nome");
await key("Escape");

// gráfico MGLU3 com RSI e linha de inspeção (recarrega para limpar a barra de comando)
await send("Page.navigate", { url: APP + "?r=1#cmd=MGLU3+B3+CHART+1D+2Y" }); await sleep(4500);   // recarga completa limpa a barra
await clickEl(`[...document.querySelectorAll('button.btn')].find(b=>b.textContent.startsWith('Estudos'))`); await sleep(700);
await clickEl(`[...document.querySelectorAll('button.chip')].find(b=>b.textContent.startsWith('+ RSI'))`); await sleep(1000);
await clickEl(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Fechar')`); await sleep(1200);
{ const c = await rect(`document.querySelector('canvas')`); await mouse(c.l + c.w * 0.78, c.t + c.h * 0.3); }
await shot("03-grafico-analise-tecnica");

// demonstrações + fonte da célula
await run("PETR4 B3 FIN Q"); await sleep(3000);
await js(`document.querySelector('.grid').focus()`);
await key("ArrowDown"); await key("ArrowDown"); await key("Enter"); await sleep(1500);
await mouse(1900, 1070);
await shot("04-demonstracoes-com-fonte");
await key("s"); await sleep(2500);
await shot("05-documento-original-cvm");
await key("Escape"); await sleep(800);

await run("WEGE3 B3 VALUE"); await sleep(3500); await shot("06-valuation-multiplos-dcf");
await run("COMPARE PETR4:B3 VALE3:B3 ITUB4:B3"); await sleep(3500); await shot("07-comparacao");
await run("NEWS WORLD"); await sleep(3000);
await clickEl(`[...document.querySelectorAll('table.tbl tr[tabindex]')].find(x=>{const b=x.getBoundingClientRect(); return b.x>300 && b.x<900 && b.y>150;})`); await sleep(2000);
await mouse(1900, 1070);
await shot("08-central-de-noticias");
await run("SCAN BR"); await sleep(800);
for (let i = 0; i < 60 && !(await js(`[...document.querySelectorAll('button.btn.pri')].some(b=>b.textContent.trim()==='Rodar')`)); i++) await sleep(250);
await sleep(1000); await shot("09-rastreador");
await run("MACRO BR SELIC"); await sleep(3000); await shot("10-macro-selic");
await run("AAPL NASDAQ CHART 1D 1Y"); await sleep(3000);
{ const c = await rect(`document.querySelector('canvas')`); await mouse(c.l + c.w * 0.85, c.t + c.h * 0.3); }
await shot("11-eua-apple");

ws.close(); chrome.kill(); process.exit(0);
