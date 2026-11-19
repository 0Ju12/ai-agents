"use strict";
// 조리 모드(단계 카드 · 넣기 애니메이션 · 타이머 · 음성) / 사진 기록 / 바코드 등록
let guide = null,
  stepAt = 0,
  clock = 0,
  remain = 0,
  photoResult = null;
const vessel = { drop: "🍲", stir: "🍳", boil: "🍲", steam: "♨️", grill: "🍳", mix: "🥣", chop: "🔪", blanch: "🫕", ready: "🍽️" };

function speak(text) {
  if (window.HankkiVoice) return window.HankkiVoice.speak(text);
  if ("speechSynthesis" in window) {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    speechSynthesis.speak(u);
  } else note("이 기기에서는 음성 안내를 지원하지 않아요.");
}
function stopVoice() {
  if (window.HankkiVoice) window.HankkiVoice.stop();
  else if ("speechSynthesis" in window) speechSynthesis.cancel();
}
function mmss(s) {
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}
function stopClock() {
  clearInterval(clock);
  clock = 0;
}
let tab = "anim",
  mediaInfo = null,
  videoAt = 0,
  igLoaded = false;
function fxLayer(card) {
  // 동작별 효과: 김·기포(끓이기·찌기·데치기), 기름 튐(볶기·굽기), 재료 떨어짐(넣기), 휘젓기(섞기), 칼질(썰기)
  const anim = card["애니메이션"],
    items = card["재료"].length ? card["재료"] : [{ 아이콘: guide["대표 아이콘"] }];
  const steam = `<div class="fx-steam"><i></i><i></i><i></i><i></i></div>`;
  const sparks = `<div class="fx-sparks">${"<i></i>".repeat(8)}</div>`;
  const drops = `<div class="fx-drop">${items.map((x, i) => `<span style="--i:${i}">${esc(x["아이콘"])}</span>`).join("")}</div>`;
  return (
    {
      boil: steam,
      steam: steam,
      blanch: steam + drops,
      stir: sparks + `<div class="fx-toss">${items.map((x, i) => `<span style="--i:${i}">${esc(x["아이콘"])}</span>`).join("")}</div>`,
      grill: sparks,
      drop: drops,
      mix: `<div class="fx-swirl"></div>`,
      chop: `<div class="fx-knife">🔪</div>`,
    }[anim] || ""
  );
}
function stage(card) {
  // 우선순위: 검수 승인된 AI 클립 → 단계 사진 + 움직임(깊이 맵이 있으면 2.5D) → 재료 아이콘 애니메이션
  if (card["클립"])
    return `<figure class="cook-photo"><video src="${esc(card["클립"])}" autoplay muted loop playsinline aria-label="${esc(card["순서"] + "단계 조리 장면")}"></video><figcaption>AI 생성 조리 장면 · 검수 완료 · 실제와 다를 수 있어요</figcaption></figure>`;
  if (card["사진"])
    return `<figure class="cook-photo cook-scene anim-${esc(card["애니메이션"])}"><img class="kb" src="${esc(card["사진"])}" alt="${esc(card["순서"] + "단계 조리 사진")}" onerror="this.closest('figure').classList.add('broken')">${card["깊이"] ? `<canvas class="depth3d" data-img="${esc(card["사진"])}" data-depth="${esc(card["깊이"])}" aria-hidden="true"></canvas>` : ""}<div class="scene-fx" aria-hidden="true">${fxLayer(card)}</div><figcaption>식품안전나라 조리 과정 사진${card["깊이"] ? " · 입체 움직임" : ""}</figcaption></figure>`;
  return kitchenScene(card, guide["대표 아이콘"]);
}
function tabs() {
  return `<div class="cook-tabs" role="tablist">${[
    ["anim", "애니메이션"],
    ["video", "영상"],
    ["social", "인기 레시피"],
  ]
    .map(([k, n]) => `<button type="button" role="tab" aria-selected="${tab === k}" class="chip ${tab === k ? "on" : ""}" data-do="cookTab" data-arg="${k}">${n}</button>`)
    .join("")}</div>`;
}
function providerNote(r, label) {
  return `<p class="hint">${esc(errors[r?.error] || label + " 자료를 확인하지 못했어요.")}${r?.setting ? " · " + esc(r.setting) : ""}</p>`;
}
function videoPane() {
  if (!mediaInfo) return '<p class="hint" role="status">영상을 찾고 있어요…</p>';
  const yt = mediaInfo.youtube;
  if (!yt.ok) return providerNote(yt, "YouTube") + a("YouTube에서 직접 찾기", mediaInfo["직접 검색"].YouTube) + linkForm(guide["메뉴"]);
  const v = yt.data[videoAt],
    start = v.step_starts[stepAt];
  return `<div class="video-wrap"><iframe src="https://www.youtube.com/embed/${esc(v.id)}?start=${start || 0}&rel=0&playsinline=1" title="${esc(v.title)}" allow="encrypted-media; picture-in-picture; fullscreen" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen loading="lazy"></iframe></div>
  <p class="hint">${start != null ? `이 단계 장면(${mmss(start)})부터 재생해요 · ${esc(v.matching)}` : v.chapters.length ? "이 단계와 맞는 챕터가 없어 처음부터 재생해요." : "챕터가 없는 영상이라 처음부터 재생해요."} · ${esc(v.channel)}</p>
  ${v.chapters.length ? `<details><summary>챕터 ${v.chapters.length}개</summary><div class="btnbar">${v.chapters.map((c) => btn(mmss(c.start) + " " + c.title, "cookSeek", "chip", "", c.start)).join("")}</div></details>` : ""}
  <div class="btnbar">${yt.data.map((x, i) => btn((i === videoAt ? "▶ " : "") + x.title.slice(0, 26), "cookVideo", "chip", "", i)).join("")}</div><p class="footnote">${esc(yt.source)}</p>${linkForm(guide["메뉴"])}`;
}
function socialPane() {
  if (!mediaInfo) return '<p class="hint" role="status">게시물을 찾고 있어요…</p>';
  const ig = mediaInfo.instagram;
  if (!ig.ok || !ig.data.length)
    return providerNote(ig, "Instagram") + `<p>${a("Instagram 해시태그에서 보기", mediaInfo["직접 검색"].Instagram)}</p><p class="footnote">해시태그 자동 조회는 Instagram 비즈니스 계정 연결과 Meta 앱 검수가 필요해요.</p>` + linkForm(guide["메뉴"]);
  return (
    ig.data
      .slice(0, 3)
      .map((x) => `<blockquote class="instagram-media" data-instgrm-permalink="${esc(x.url)}" data-instgrm-version="14"><a href="${esc(x.url)}" rel="noopener noreferrer">${esc(x.title)}</a></blockquote>`)
      .join("") + `<p class="footnote">${esc(ig.source)}</p>` + linkForm(guide["메뉴"])
  );
}
function loadInstagram() {
  if (window.instgrm) return window.instgrm.Embeds.process();
  if (igLoaded) return;
  igLoaded = true;
  const sc = document.createElement("script");
  sc.src = "https://www.instagram.com/embed.js";
  sc.async = true;
  document.body.appendChild(sc);
}
async function ensureMedia() {
  if (mediaInfo) return;
  const r = await api("/api/guide/media", "POST", { menu: guide["메뉴"], steps: guide["단계"].map((c) => c["설명"]) });
  mediaInfo = r;
  if (dialog.open && guide && $("#sheet-body .cook")) paint(); // 다른 화면으로 바뀌었으면 덮어쓰지 않는다
}
function cookCard() {
  const card = guide["단계"][stepAt],
    total = guide["단계"].length,
    last = stepAt === total - 1;
  const full = dialog.classList.contains("cook-full"),
    secs = card["타이머(초)"];
  return `<div class="cook">
  <div class="cook-progress" aria-label="${stepAt + 1}/${total}단계"><i style="width:${((stepAt + 1) / total) * 100}%"></i></div>
  <div class="serv-row"><span>분량</span>${btn("−", "cookServ", "chip", "", -1)}<b>${guide["인분"]}인분</b>${btn("+", "cookServ", "chip", "", 1)}</div>
  <div class="cook-head"><p class="eyeline">${stepAt + 1} / ${total}단계 · ${esc(card["동작"])}${card["불 세기"] ? ` · <span class="cook-heat">🔥 ${esc(card["불 세기"])}</span>` : ""}</p>${btn(full ? "작게 보기" : "크게 보기", "cookFull", "linkbtn", "panels-top-left")}</div>
  <div class="step-dots" aria-label="단계 이동">${guide["단계"].map((c, i) => `<button type="button" data-do="cookGo" data-arg="${i}" class="${i === stepAt ? "on" : i < stepAt ? "done" : ""}" aria-label="${i + 1}단계${i === stepAt ? " (현재)" : ""}">${i + 1}</button>`).join("")}</div>
  ${tabs()}
  <div class="cook-body">${tab === "anim" ? stage(card) + stepVideoButton() : tab === "video" ? videoPane() : socialPane()}</div>
  <p class="cook-text">${esc(card["설명"])}</p>
  ${card["팁"] ? `<p class="hint">${esc(card["팁"])}</p>` : ""}
  ${card["재료"].length ? `<div class="btnbar">${card["재료"].map((x) => `<span class="pill ${x["보유"] ? "" : "warn"}">${esc(x["아이콘"] + " " + x["이름"])}${x["분량(g)"] != null ? " " + fmt(x["분량(g)"]) + "g" : ""}${x["보유"] ? "" : " · 미보유"}</span>`).join("")}</div>` : ""}
  ${secs ? `<div class="cook-timer"><div class="cook-ring" id="cook-ring" style="--p:${Math.round((1 - (remain || secs) / secs) * 100)}"><b id="cook-clock">${mmss(remain || secs)}</b></div><div><strong>${Math.round(secs / 60)}분 타이머</strong><p class="hint">원문에 적힌 시간이에요. 끝나면 진동과 음성으로 알려 드려요.</p></div>${btn(clock ? "일시정지" : "시작", "cookTimer", "btn alt", "timer")}</div>` : ""}
  <div class="cook-nav">${btn("이전", "cookPrev", "btn alt", "chevron-left")}${btn("읽어주기", "cookSpeak", "btn alt", "volume-2")}${last ? btn("조리 완료 기록", "cookDone", "btn", "check") : btn("다음", "cookNext", "btn", "chevron-right")}</div>
  <details><summary>전체 재료 (${guide["인분"]}인분)</summary><p>${guide["재료 합계"].map((x) => esc(x["아이콘"] + " " + x["이름"]) + (x["분량(g)"] != null ? " " + fmt(x["분량(g)"]) + "g" : "")).join(" · ")}</p><p class="hint">${esc(guide["안내"])} · ${esc(guide["출처"])} · ${esc(guide["판단 방법"])}</p></details></div>`;
}
function paint() {
  $("#sheet-body").innerHTML = cookCard();
  document.querySelectorAll("#sheet-body canvas.depth3d").forEach(depth3d);
  if (tab === "social" && mediaInfo?.instagram?.ok) loadInstagram();
}
function showStep(i) {
  stopClock();
  stopVoice();
  stepAt = Math.max(0, Math.min(i, guide["단계"].length - 1));
  remain = guide["단계"][stepAt]["타이머(초)"] || 0;
  paint();
}
function depth3d(canvas) {
  // 2.5D: 깊이 맵만큼 사진의 각 점을 다르게 밀어, 카메라가 천천히 움직이는 것처럼 보이게 한다 (WebGL)
  const gl = canvas.getContext("webgl", { premultipliedAlpha: false });
  if (!gl || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const load = (src) => new Promise((ok, no) => Object.assign(new Image(), { onload() { ok(this); }, onerror: no, src }));
  Promise.all([load(canvas.dataset.img), load(canvas.dataset.depth)]).then(([img, dep]) => {
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    gl.viewport(0, 0, canvas.width, canvas.height);
    const sh = (type, src) => { const x = gl.createShader(type); gl.shaderSource(x, src); gl.compileShader(x); return x; };
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, "attribute vec2 p;varying vec2 uv;void main(){uv=vec2(p.x*.5+.5,.5-p.y*.5);gl_Position=vec4(p,0,1);}"));
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, "precision mediump float;uniform sampler2D img,dep;uniform vec2 off;varying vec2 uv;void main(){float d=texture2D(dep,uv).r;vec2 q=uv+off*(d-.5);q=.5+(q-.5)*.94;gl_FragColor=texture2D(img,q);}"));
    gl.linkProgram(prog);
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    [img, dep].forEach((im, i) => {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, im);
      gl.uniform1i(gl.getUniformLocation(prog, i ? "dep" : "img"), i);
    });
    const off = gl.getUniformLocation(prog, "off");
    let tilt = [0, 0];
    addEventListener("deviceorientation", (e) => (tilt = [(e.gamma || 0) / 900, (e.beta - 45 || 0) / 900]), { passive: true });
    canvas.closest("figure").classList.add("has-depth");
    const t0 = performance.now();
    (function frame(t) {
      if (!canvas.isConnected) return;
      const k = (t - t0) / 1000;
      gl.uniform2f(off, 0.03 * Math.sin(k * 0.6) + tilt[0], 0.015 * Math.cos(k * 0.45) + tilt[1]);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      requestAnimationFrame(frame);
    })(t0);
  }).catch(() => {});
}
let guideReq = null;
async function openGuide(req) {
  // 인분은 조리 모드 안의 − / + 로 바꾼다 (기본 1인분 또는 코치가 정한 인분)
  guideReq = { title: req.title, recipe_id: req.recipe_id };
  markWaiting("조리 단계를 준비하고 있어요…");
  try {
    guide = await api("/api/guide", "POST", { ...guideReq, servings: req.servings || 1 });
  } finally {
    document.querySelectorAll("#main [data-progress]").forEach((el) => el.remove());
  }
  mediaInfo = null;
  videoAt = 0;
  tab = "anim";
  sheet(guide["메뉴"] + " · 조리 모드", "");
  showStep(0);
  ensureMedia().catch(() => {}); // 실제 영상을 미리 찾아 두고, 단계와 맞는 장면이 있으면 버튼을 띄운다
}
function stepVideoButton() {
  const yt = mediaInfo?.youtube;
  if (!yt?.ok) return "";
  const i = yt.data.findIndex((v) => v.step_starts?.[stepAt] != null);
  if (i < 0) return "";
  return btn(`이 단계 실제 영상 보기 (${mmss(yt.data[i].step_starts[stepAt])})`, "cookStepVideo", "btn alt video-cue", "circle-play", i);
}
function readFile(input, max = 1280) {
  // 업로드 전에 긴 변을 1280px 로 줄여 JPEG 로 보낸다 (전송량·처리 시간 절감)
  return new Promise((resolve, reject) => {
    const file = input.files?.[0];
    if (!file) return reject(Error("사진을 선택하세요."));
    const img = new Image(),
      url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height)),
        c = document.createElement("canvas");
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => reject(Error("사진을 읽지 못했어요."));
    img.src = url;
  });
}
function photoForm(kind) {
  const meal = kind === "meal";
  return `<form class="form" data-form="photo" data-kind="${kind}"><p class="hint">${meal ? "먹은 음식을 찍으면 음식 후보와 대략적인 양을 보여드려요. 열량은 확인한 이름과 g으로 공공 영양 참조값에서 계산해요." : "냉장고나 장바구니를 찍으면 재료 후보를 보여드려요. 선택한 재료만 등록돼요."}</p>
  <label>사진<input name="image" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" required></label>
  <p class="footnote">사진은 서버에 저장하지 않고 분석에만 사용해요. 모델 키가 없으면 직접 입력으로 안내해요.</p>
  <button class="btn" type="submit">${ic("camera")}사진 분석</button></form>`;
}
function photoReview(r) {
  if (!r.ok) return `<p>${esc(r["안내"] || errors[r.error] || "사진을 분석하지 못했어요.")}</p>${btn("직접 입력", r.kind === "meal" || photoKind === "meal" ? "water" : "lot", "btn alt")}`;
  const meal = r.kind === "meal";
  const rows = r["후보"]
    .map(
      (x, i) =>
        `<div class="list-line"><label class="check"><input type="checkbox" name="pick" value="${i}" ${x.confidence >= 0.4 ? "checked" : ""}> <strong>${esc(x.name)}</strong> <small>확신도 ${Math.round(x.confidence * 100)}%${x["보유"] ? " · 이미 보유" : ""}${meal && !x["영양 참조"] ? " · 영양 참조 없음" : ""}</small></label>${meal ? `<input class="grams" name="g${i}" type="number" min="1" max="3000" value="${x.grams ?? ""}" placeholder="g" aria-label="${esc(x.name)} 양(g)" required>` : `<input type="hidden" name="n${i}" value="${esc(x.name)}">`}</div>`,
    )
    .join("");
  return `<form class="form" data-form="photoSave" data-kind="${r.kind}">${rows || '<p class="empty">찾은 후보가 없어요.</p>'}${r["메모"] ? `<p class="hint">${esc(r["메모"])}</p>` : ""}
  ${meal && r["예상 영양"]?.["합계"] ? `<p class="hint">예상 합계 · ${fmt(r["예상 영양"]["합계"].kcal)} kcal · 단백질 ${fmt(r["예상 영양"]["합계"].protein_g)} g (저장 시 확인한 g 으로 다시 계산)</p>` : ""}
  <p class="footnote">${esc(r["안내"])}</p><button class="btn" type="submit">${ic("check")}${meal ? "식사로 기록" : "선택한 재료 냉장고에 넣기"}</button></form>`;
}
let photoKind = "meal";
function barcodeForm() {
  const live = "BarcodeDetector" in window;
  return `<form class="form" data-form="barcode"><p class="hint">${live ? "포장 바코드를 찍거나 숫자를 입력하세요." : "이 기기는 사진 바코드 인식을 지원하지 않아요. 숫자를 입력하세요."}</p>
  ${live ? `<label>바코드 사진<input name="image" type="file" accept="image/*" capture="environment"></label>` : ""}
  ${field("바코드 숫자", "code", "text", "", "inputmode=numeric pattern='[0-9]{8,14}' placeholder='8~14자리'")}
  <button class="btn" type="submit">${ic("search")}제품 확인</button><p class="footnote">제품 정보 · Open Food Facts</p></form>`;
}
async function scanBarcode(input) {
  const file = input?.files?.[0];
  if (!file || !("BarcodeDetector" in window)) return "";
  const found = await new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] }).detect(await createImageBitmap(file));
  return found[0]?.rawValue || "";
}
Object.assign(action, {
  cookMode: (title) => openGuide({ title }),
  cookModeExt: (id) => openGuide({ recipe_id: id }),
  cookTab: async (k) => {
    tab = k;
    paint();
    if (k !== "anim") await ensureMedia();
  },
  cookVideo: (i) => {
    videoAt = Number(i);
    paint();
  },
  cookSeek: (sec) => {
    const f = $("#sheet-body .video-wrap iframe");
    if (f) f.src = f.src.replace(/start=\d+/, "start=" + Number(sec)) + (f.src.includes("autoplay") ? "" : "&autoplay=1");
  },
  cookNext: () => showStep(stepAt + 1),
  cookServ: async (d) => {
    const servings = Math.max(1, Math.min(20, guide["인분"] + Number(d)));
    if (servings === guide["인분"]) return;
    const at = stepAt;
    guide = await api("/api/guide", "POST", { ...guideReq, servings });
    stepAt = at;
    paint();
  },
  cookStepVideo: (i) => {
    videoAt = Number(i);
    tab = "video";
    paint();
  },
  cookGo: (i) => showStep(Number(i)),
  cookFull: () => {
    dialog.classList.toggle("cook-full");
    paint();
  },
  cookPrev: () => showStep(stepAt - 1),
  cookSpeak: () => {
    const c = guide["단계"][stepAt];
    speak(`${stepAt + 1}단계. ${c["설명"]}`);
  },
  cookTimer: () => {
    if (clock) {
      stopClock();
      paint();
      return;
    }
    clock = setInterval(() => {
      remain = Math.max(0, remain - 1);
      const el = $("#cook-clock"),
        ring = $("#cook-ring"),
        total = guide["단계"][stepAt]["타이머(초)"] || 1;
      if (el) el.textContent = mmss(remain);
      if (ring) ring.style.setProperty("--p", Math.round((1 - remain / total) * 100));
      if (!remain) {
        stopClock();
        navigator.vibrate?.([300, 120, 300]);
        speak("타이머가 끝났어요. 다음 단계를 확인하세요.");
        if (el) paint();
      }
    }, 1000);
    paint();
  },
  cookDone: () => {
    stopClock();
    stopVoice();
    action.cook();
  },
  photoMeal: () => {
    photoKind = "meal";
    sheet("식사 사진 기록", photoForm("meal"));
  },
  photoFridge: () => {
    photoKind = "fridge";
    sheet("사진으로 재료 등록", photoForm("fridge"));
  },
  barcode: () => sheet("바코드로 재료 등록", barcodeForm()),
});
Object.assign(forms, {
  photo: async (v, f) => {
    const image = await readFile(f.querySelector("input[type=file]"));
    markWaiting("사진 속 후보를 찾고 있어요…");
    photoResult = await api("/api/photo", "POST", { kind: f.dataset.kind, image });
    $("#sheet-body").innerHTML =
      photoReview(photoResult) +
      `<details><summary>이번 실행 과정 (${photoResult["추적"].length}단계)</summary>${trace(photoResult["추적"])}</details>`;
  },
  photoSave: async (v, f) => {
    const picks = [...f.querySelectorAll("input[name=pick]:checked")].map((x) => Number(x.value));
    if (!picks.length) throw Error("기록할 후보를 선택하세요.");
    if (f.dataset.kind === "meal")
      return send("사진식사", {
        items: picks.map((i) => ({ name: photoResult["후보"][i].name, grams: Number(f.elements["g" + i].value) })),
      });
    return send("입고", { name: picks.map((i) => photoResult["후보"][i].name).join(", "), quantity: null });
  },
  barcode: async (v, f) => {
    const code = (await scanBarcode(f.querySelector("input[type=file]")).catch(() => "")) || (v.code || "").trim();
    if (!/^\d{8,14}$/.test(code)) throw Error("바코드를 인식하지 못했어요. 숫자를 입력하세요.");
    const r = await api("/api/barcode/" + code);
    if (!r.ok) throw Error(errors[r.error] || "제품 정보를 찾지 못했어요.");
    action.lot();
    const name = $("#sheet-body input[name=name]");
    if (name) name.value = r.data.product || "";
    markWaiting(`${r.data.product || "제품"} · 표시 영양 ${r.data.basis || ""} ${fmt(r.data.kcal)} kcal · 이름과 중량을 확인하세요.`);
  },
});
dialog.addEventListener("close", () => {
  stopClock();
  stopVoice();
  dialog.classList.remove("cook-full");
});
