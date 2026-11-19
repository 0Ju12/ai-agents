"use strict";
// 조리 장면(SVG): 동작마다 도구·불·재료 움직임을 그린다. 사진이 없는 단계와 사진 위 효과 모두에 쓴다.
// 동작: drop(넣기) stir(볶기) grill(굽기) boil(끓이기) blanch(데치기) steam(찌기) mix(섞기) chop(썰기) ready(준비)
const HEAT_SCALE = { 약불: 0.55, 중약불: 0.7, 중불: 0.85, 중강불: 1, 강불: 1.15, 센불: 1.15 };
const HEATED = new Set(["boil", "blanch", "steam", "stir", "grill"]);

function svgEmoji(ch, x, y, size, cls = "", i = 0) {
  return `<text class="ks-food ${cls}" x="${x}" y="${y}" font-size="${size}" text-anchor="middle" dominant-baseline="central" style="--i:${i}">${esc(ch)}</text>`;
}
function flames(heat) {
  const k = HEAT_SCALE[heat] || 0.85;
  const one = (x, d) =>
    `<path class="ks-flame" style="--d:${d}s" d="M${x} 262 q-9 -14 0 -${30 * k} q9 ${14 * k} 0 ${30 * k}z" fill="url(#ks-fire)"/>`;
  return `<g class="ks-burner"><ellipse cx="200" cy="266" rx="92" ry="9" fill="#2c3a33"/>${[150, 175, 200, 225, 250].map((x, i) => one(x, (i % 3) * 0.13)).join("")}</g>`;
}
function steamPuffs(y = 120) {
  return `<g class="ks-steam">${[170, 200, 230]
    .map((x, i) => `<path style="--d:${i * 0.7}s" d="M${x} ${y} c-12 -16 12 -26 0 -42 c-12 -16 12 -26 0 -42" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round"/>`)
    .join("")}</g>`;
}
function pot(items, kind) {
  const lid = kind === "steam";
  return `<g class="ks-pot">
    <rect x="118" y="158" width="164" height="82" rx="18" fill="#c8d3cf"/><rect x="118" y="158" width="164" height="18" rx="9" fill="#e3ebe8"/>
    <rect x="96" y="170" width="26" height="10" rx="5" fill="#9fb0a9"/><rect x="278" y="170" width="26" height="10" rx="5" fill="#9fb0a9"/>
    <clipPath id="ks-potclip"><rect x="124" y="164" width="152" height="70" rx="14"/></clipPath>
    <g clip-path="url(#ks-potclip)"><rect x="124" y="176" width="152" height="60" fill="#8fc3d6"/>
      ${[140, 165, 190, 215, 240, 262].map((x, i) => `<circle class="ks-bubble" style="--d:${(i * 0.37) % 1.6}s" cx="${x}" cy="230" r="${4 + (i % 3) * 2}" fill="#e9f6fb"/>`).join("")}
      ${items.slice(0, 4).map((x, i) => svgEmoji(x, 150 + i * 34, 190, 26, "ks-bob", i)).join("")}</g>
    ${lid ? `<g class="ks-lid"><rect x="112" y="140" width="176" height="16" rx="8" fill="#b7c4bf"/><rect x="186" y="128" width="28" height="14" rx="6" fill="#8ea19a"/></g>` : ""}
  </g>${steamPuffs(lid ? 128 : 150)}`;
}
function pan(items, grill) {
  return `<g class="ks-pan"><ellipse cx="190" cy="222" rx="104" ry="24" fill="#3a3f3d"/><ellipse cx="190" cy="216" rx="94" ry="18" fill="#555b58"/>
    <rect x="288" y="210" width="96" height="14" rx="7" fill="#6b4f3a"/>
    ${items.slice(0, 4).map((x, i) => svgEmoji(x, 140 + i * 34, 206, 28, "ks-hop", i)).join("")}</g>
    <g class="ks-sizzle">${Array.from({ length: 9 }, (_, i) => `<circle style="--d:${(i * 0.21) % 0.9}s;--dx:${(i % 3) * 18 - 18}px" cx="${130 + i * 14}" cy="200" r="3" fill="${grill ? "#ffb02e" : "#ffd36b"}"/>`).join("")}</g>`;
}
function bowl(items, whisk = true) {
  return `<g class="ks-bowl"><path d="M100 170 h200 a100 70 0 0 1 -200 0z" fill="#e9e2d0" stroke="#cfc5ad" stroke-width="3"/><path d="M100 170 h200" stroke="#d8d2c2" stroke-width="6" stroke-linecap="round"/>
    <g class="ks-orbit">${items.slice(0, 4).map((x, i) => svgEmoji(x, 200 + Math.cos(i * 1.6) * 40, 190 + Math.sin(i * 1.6) * 12, 26, "", i)).join("")}</g>
    ${whisk ? `<g class="ks-whisk"><line x1="200" y1="110" x2="210" y2="196" stroke="#9aa5a0" stroke-width="6" stroke-linecap="round"/><ellipse cx="211" cy="196" rx="14" ry="22" fill="none" stroke="#9aa5a0" stroke-width="3"/></g>` : ""}</g>`;
}
function board(items) {
  const food = items[0] || "🥕";
  return `<g class="ks-board"><rect x="70" y="200" width="260" height="44" rx="12" fill="#c99a62"/><rect x="70" y="200" width="260" height="10" rx="5" fill="#ddb37d"/>
    ${svgEmoji(food, 170, 186, 44, "ks-whole")}
    ${[0, 1, 2].map((i) => svgEmoji(food, 236 + i * 24, 196, 20, "ks-piece", i)).join("")}
    <g class="ks-knife"><path d="M190 120 l70 -8 l4 14 l-74 22z" fill="#dfe5e3" stroke="#aab4b0" stroke-width="2"/><rect x="258" y="104" width="46" height="14" rx="6" fill="#3d3d3d" transform="rotate(-6 258 104)"/></g></g>`;
}
function dropScene(items, inPot) {
  const target = inPot
    ? `<rect x="122" y="170" width="156" height="70" rx="16" fill="#c8d3cf"/><rect x="128" y="182" width="144" height="10" rx="5" fill="#8fc3d6"/>`
    : `<path d="M110 176 h180 a90 62 0 0 1 -180 0z" fill="#e9e2d0" stroke="#cfc5ad" stroke-width="3"/><ellipse cx="200" cy="178" rx="88" ry="10" fill="#f7f2e6"/>`;
  return `<g class="ks-drop">${target}
    ${items.slice(0, 4).map((x, i) => svgEmoji(x, 160 + i * 28, 60, 30, "ks-fall", i)).join("")}
    <g class="ks-ripple">${[0, 1].map((i) => `<ellipse style="--d:${i * 0.9}s" cx="200" cy="184" rx="20" ry="5" fill="none" stroke="#fff" stroke-width="3"/>`).join("")}</g></g>`;
}
function plate(items, icon) {
  return `<g class="ks-plate"><ellipse cx="200" cy="222" rx="120" ry="26" fill="#fff"/><ellipse cx="200" cy="218" rx="90" ry="18" fill="#f3f1ea"/>
    ${svgEmoji(icon, 200, 190, 64, "ks-dish")}
    ${items.slice(0, 3).map((x, i) => svgEmoji(x, 110 + i * 90, 120, 24, "ks-twinkle", i)).join("")}
    ${[0, 1, 2].map((i) => `<path class="ks-spark" style="--d:${i * 0.5}s" d="M${140 + i * 60} ${100 - (i % 2) * 20} l4 10 l10 4 l-10 4 l-4 10 l-4 -10 l-10 -4 l10 -4z" fill="#ffd36b"/>`).join("")}</g>`;
}
function kitchenScene(card, icon) {
  const anim = card["애니메이션"] || "ready",
    items = (card["재료"] || []).map((x) => x["아이콘"]),
    list = items.length ? items : [icon || "🍲"],
    text = card["설명"] || "";
  const body =
    { boil: pot(list, "boil"), blanch: pot(list, "blanch"), steam: pot(list, "steam"), stir: pan(list, false), grill: pan(list, true), mix: bowl(list), chop: board(list), drop: dropScene(list, /냄비|끓는|물에|국물/.test(text)), ready: plate(list, icon || "🍽️") }[anim] ||
    plate(list, icon || "🍽️");
  return `<svg class="ks ks-${esc(anim)}" viewBox="0 0 400 300" role="img" aria-label="${esc((card["동작"] || "") + " 장면")}">
    <defs><linearGradient id="ks-wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbfaf2"/><stop offset="1" stop-color="#e7f1d4"/></linearGradient>
      <linearGradient id="ks-fire" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#ff7a1a"/><stop offset=".6" stop-color="#ffb02e"/><stop offset="1" stop-color="#ffe08a"/></linearGradient></defs>
    <rect width="400" height="300" fill="url(#ks-wall)"/><rect y="250" width="400" height="50" fill="#d9c8a8"/><rect y="250" width="400" height="6" fill="#c7b38f"/>
    ${HEATED.has(anim) ? flames(card["불 세기"]) : ""}${body}</svg>`;
}
