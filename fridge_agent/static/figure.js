"use strict";
// 운동 동작 애니메이션(SVG): 관절 좌표로 시작·끝 자세를 정하고 SMIL 로 선을 변형한다. 오른쪽을 보는 옆모습.
// 관절: h 머리, n 어깨, p 골반, e1/w1 앞팔 팔꿈치·손, e2/w2 뒷팔, k1/f1 앞다리 무릎·발, k2/f2 뒷다리
const STAND = { h: [200, 86], n: [200, 104], p: [200, 172], e1: [203, 137], w1: [205, 168], e2: [197, 137], w2: [195, 168], k1: [203, 215], f1: [205, 257], k2: [197, 215], f2: [195, 257] };
const pose = (over) => ({ ...STAND, ...over });
const both = (e, w) => ({ e1: e, w1: w, e2: [e[0] - 4, e[1]], w2: [w[0] - 4, w[1]] });
const FIGURE = {
  walk: { dur: 1.1, poses: [pose({ k1: [214, 213], f1: [222, 254], k2: [190, 214], f2: [180, 256], e1: [188, 134], w1: [182, 162], e2: [214, 134], w2: [226, 158] }), pose({ k1: [190, 214], f1: [180, 256], k2: [214, 213], f2: [222, 254], e1: [214, 134], w1: [226, 158], e2: [188, 134], w2: [182, 162] })] },
  squat: { dur: 2.6, poses: [pose(both([228, 106], [258, 108])), pose({ h: [214, 122], n: [208, 140], p: [178, 204], ...both([238, 140], [268, 142]), k1: [222, 214], f1: [206, 257], k2: [218, 216], f2: [202, 257] })] },
  lunge: { dur: 2.6, poses: [pose(both([212, 150], [206, 172])), pose({ h: [200, 112], n: [200, 130], p: [200, 198], ...both([212, 176], [206, 198]), k1: [240, 214], f1: [242, 257], k2: [176, 242], f2: [138, 256] })] },
  wallpush: { dur: 2.4, prop: "wall", poses: [pose({ h: [258, 96], n: [250, 112], p: [222, 180], ...both([270, 112], [290, 112]), k1: [212, 219], f1: [202, 257], k2: [210, 219], f2: [198, 257] }), pose({ h: [272, 100], n: [264, 117], p: [228, 182], ...both([266, 136], [290, 114]), k1: [214, 220], f1: [202, 257], k2: [212, 220], f2: [198, 257] })] },
  incline: { dur: 2.4, prop: "bench", poses: [pose({ h: [286, 138], n: [270, 150], p: [192, 205], ...both([281, 178], [288, 205]), k1: [150, 232], f1: [110, 257], k2: [148, 232], f2: [106, 257] }), pose({ h: [290, 166], n: [274, 178], p: [194, 215], ...both([256, 194], [288, 205]), k1: [150, 238], f1: [110, 257], k2: [148, 238], f2: [106, 257] })] },
  pushup: { dur: 2.4, prop: "mat", poses: [pose({ h: [290, 198], n: [272, 206], p: [190, 228], ...both([272, 232], [274, 258]), k1: [150, 242], f1: [110, 256], k2: [150, 243], f2: [108, 256] }), pose({ h: [292, 230], n: [274, 238], p: [190, 244], ...both([252, 246], [274, 258]), k1: [150, 250], f1: [110, 256], k2: [150, 251], f2: [108, 256] })] },
  plank: { dur: 3.2, prop: "mat", poses: [pose({ h: [286, 220], n: [268, 228], p: [190, 234], e1: [268, 256], w1: [298, 256], e2: [264, 256], w2: [294, 256], k1: [150, 245], f1: [110, 256], k2: [150, 246], f2: [108, 256] }), pose({ h: [286, 218], n: [268, 226], p: [190, 228], e1: [268, 256], w1: [298, 256], e2: [264, 256], w2: [294, 256], k1: [150, 242], f1: [110, 256], k2: [150, 243], f2: [108, 256] })] },
  shouldertap: { dur: 1.6, prop: "mat", poses: [pose({ h: [290, 198], n: [272, 206], p: [190, 228], ...both([272, 232], [274, 258]), k1: [150, 242], f1: [110, 256], k2: [150, 243], f2: [108, 256] }), pose({ h: [290, 198], n: [272, 206], p: [190, 228], e1: [290, 224], w1: [268, 210], e2: [268, 232], w2: [270, 258], k1: [150, 242], f1: [110, 256], k2: [150, 243], f2: [108, 256] })] },
  birddog: { dur: 2.8, prop: "mat", poses: [pose({ h: [268, 190], n: [250, 200], p: [170, 202], ...both([250, 230], [250, 258]), k1: [172, 256], f1: [130, 256], k2: [168, 256], f2: [126, 256] }), pose({ h: [268, 190], n: [250, 200], p: [170, 202], e1: [282, 196], w1: [314, 192], e2: [246, 230], w2: [246, 258], k1: [172, 256], f1: [130, 256], k2: [130, 200], f2: [90, 198] })] },
  deadbug: { dur: 2.8, prop: "mat", poses: [pose({ h: [260, 244], n: [240, 248], p: [170, 248], ...both([240, 216], [240, 186]), k1: [172, 208], f1: [208, 208], k2: [168, 208], f2: [204, 208] }), pose({ h: [260, 244], n: [240, 248], p: [170, 248], e1: [272, 240], w1: [302, 242], e2: [236, 216], w2: [236, 186], k1: [172, 208], f1: [208, 208], k2: [130, 238], f2: [92, 246] })] },
  prone: { dur: 2.6, prop: "mat", poses: [pose({ h: [260, 240], n: [240, 248], p: [170, 250], ...both([262, 254], [282, 254]), k1: [130, 252], f1: [92, 254], k2: [128, 253], f2: [90, 254] }), pose({ h: [262, 230], n: [242, 240], p: [170, 250], ...both([266, 230], [292, 220]), k1: [130, 252], f1: [92, 254], k2: [128, 253], f2: [90, 254] })] },
  wallslide: { dur: 2.6, prop: "backwall", poses: [pose(both([188, 100], [192, 72])), pose(both([194, 72], [198, 42]))] },
  raise: { dur: 2.4, poses: [pose(both([203, 137], [206, 168])), pose(both([232, 106], [262, 106]))] },
  curl: { dur: 2, poses: [pose(both([203, 137], [205, 168])), pose(both([203, 137], [222, 110]))] },
  row: { dur: 2.2, prop: "dumbbell", poses: [pose({ h: [276, 130], n: [258, 140], p: [190, 168], e1: [260, 172], w1: [262, 202], e2: [256, 172], w2: [258, 200], k1: [200, 212], f1: [198, 257], k2: [196, 212], f2: [192, 257] }), pose({ h: [276, 130], n: [258, 140], p: [190, 168], e1: [230, 132], w1: [240, 160], e2: [256, 172], w2: [258, 200], k1: [200, 212], f1: [198, 257], k2: [196, 212], f2: [192, 257] })] },
  breathe: { dur: 4, poses: [pose({}), pose(both([206, 74], [210, 44]))] },
};
const pt = (P, k) => `${P[k][0]} ${P[k][1]}`;
const seg = (P, ks) => "M" + ks.map((k) => pt(P, k)).join(" L");
const PARTS = [
  ["armB", ["n", "e2", "w2"], "#8aa597"],
  ["legB", ["p", "k2", "f2"], "#8aa597"],
  ["torso", ["n", "p"], "#224c3b"],
  ["legF", ["p", "k1", "f1"], "#224c3b"],
  ["armF", ["n", "e1", "w1"], "#224c3b"],
];
function morph(attr, a, b, dur) {
  return `<animate attributeName="${attr}" values="${a};${b};${a}" dur="${dur}s" repeatCount="indefinite" calcMode="spline" keyTimes="0;0.5;1" keySplines=".45 0 .55 1;.45 0 .55 1"/>`;
}
function propSVG(prop) {
  return (
    {
      wall: '<rect x="292" y="40" width="14" height="220" rx="3" fill="#d8cbb0"/>',
      backwall: '<rect x="176" y="30" width="12" height="230" rx="3" fill="#d8cbb0"/>',
      bench: '<rect x="276" y="205" width="70" height="12" rx="4" fill="#9b7653"/><rect x="284" y="217" width="8" height="40" fill="#7b5d41"/><rect x="330" y="217" width="8" height="40" fill="#7b5d41"/>',
      chair: '<rect x="150" y="200" width="44" height="10" rx="3" fill="#9b7653"/><rect x="150" y="140" width="8" height="70" fill="#7b5d41"/><rect x="186" y="210" width="6" height="48" fill="#7b5d41"/><rect x="152" y="210" width="6" height="48" fill="#7b5d41"/>',
      mat: '<rect x="70" y="256" width="270" height="6" rx="3" fill="#a7c79a"/>',
    }[prop] || ""
  );
}
function figureSVG(motion, prop, opts = {}) {
  const F = FIGURE[motion] || FIGURE.walk,
    [A, B] = F.poses,
    dur = (F.dur * (opts.speed || 1)).toFixed(2),
    still = opts.still || matchMedia("(prefers-reduced-motion: reduce)").matches;
  const usedProp = prop === "dumbbell" ? F.prop === "dumbbell" ? null : F.prop : prop || F.prop;
  const bell = prop === "dumbbell" || F.prop === "dumbbell";
  const lines = PARTS.map(([, ks, color]) => `<path d="${seg(A, ks)}" stroke="${color}" stroke-width="${ks.length === 2 ? 16 : 12}" stroke-linecap="round" stroke-linejoin="round" fill="none">${still ? "" : morph("d", seg(A, ks), seg(B, ks), dur)}</path>`).join("");
  const head = `<circle cx="${A.h[0]}" cy="${A.h[1]}" r="14" fill="#224c3b">${still ? "" : morph("cx", A.h[0], B.h[0], dur) + morph("cy", A.h[1], B.h[1], dur)}</circle>`;
  const db = bell ? ["w1", "w2"].map((k) => `<rect x="${A[k][0] - 9}" y="${A[k][1] - 4}" width="18" height="8" rx="3" fill="#3d3d3d">${still ? "" : morph("x", A[k][0] - 9, B[k][0] - 9, dur) + morph("y", A[k][1] - 4, B[k][1] - 4, dur)}</rect>`).join("") : "";
  return `<svg class="fig" viewBox="40 20 320 250" role="img" aria-label="${esc(opts.label || "운동 동작")}"><rect x="40" y="20" width="320" height="250" fill="url(#fig-bg)"/><defs><linearGradient id="fig-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbfaf2"/><stop offset="1" stop-color="#eef4e2"/></linearGradient></defs>
    <rect x="40" y="258" width="320" height="12" fill="#e2d6bd"/>${propSVG(usedProp)}${lines}${head}${db}</svg>`;
}
