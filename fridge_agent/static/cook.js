"use strict";
// 조리 모드(단계 카드 · 넣기 애니메이션 · 타이머 · 음성) / 사진 기록 / 바코드 등록
let guide = null,
  stepAt = 0,
  clock = 0,
  remain = 0,
  timerEnds = 0,
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
function prepBoard() {
  const tiles = guide["재료 합계"].map((x) => {
    const name = x["이름"], grams = x["분량(g)"];
    const unknown = x["분량 확인"], missing = x["부족(g)"];
    const status = unknown ? "분량 확인" : missing ? fmt(missing) + "g 부족" : x["보유"] ? (grams == null ? "보유 · 필요량 확인" : "충분") : "미보유";
    const lots = unknown ? st["포장"].filter((lot) => lot.item === name && lot.grams == null && (!lot.expires || lot.expires >= st["날짜"])) : [];
    return `<div class="prep-tile ${unknown || missing || !x["보유"] ? "missing" : ""}"><span class="pi">${esc(x["아이콘"])}</span><b>${esc(name)}</b><small>${grams == null ? "원문 분량 확인" : fmt(grams) + "g"} ${esc(x["계량"] || "")}</small><strong class="prep-status">${esc(status)}</strong>${lots.map((lot, i) => btn(lots.length > 1 ? (i + 1) + "번 포장 · " + expiry(lot.expires)[0] : "분량 입력", "measureGuideLot", "chip", "", lot.id)).join("")}</div>`;
  });
  const alreadyInCart = Object.values(st["장바구니"] || {}).some((row) => row.meal === guide["메뉴"]);
  const cart = guide["부족량(g)"] && (alreadyInCart || Object.keys(guide["부족량(g)"]).length)
    ? btn(alreadyInCart ? "장바구니 분량 맞추기" : "부족분 장바구니에 담기", "guideCart", "btn alt", "shopping-bag") : "";
  const raw = guide["재료 원문"];
  const original = raw ? `<details><summary>원문 재료와 분량</summary><p class="raw-ingredients">${esc(raw)}</p><p class="hint">제공처 원문 분량이에요. 선택한 인분에 맞춰 확인해 주세요.</p></details>` : "";
  return `<div class="prep-board">${tiles.join("")}</div>${original}${cart}`;
}
function stage(card) {
  if (card["종류"] === "prep") return prepBoard();
  const action = card["애니메이션"];
  const technique = ["chop", "stir", "grill", "boil", "blanch", "steam", "mix", "drop"].includes(action) ? action : "ready";
  const example = "/static/techniques/" + technique + ".webp";
  if (card["클립"]) {
    const autoplay = matchMedia("(prefers-reduced-motion: reduce)").matches ? "" : "autoplay";
    return `<figure class="cook-photo"><video controls ${autoplay} muted playsinline poster="${example}" src="${esc(card["클립"])}"></video><figcaption>검수된 AI 조리 영상</figcaption></figure>`;
  }
  const caption = card["사진"] ? "식품안전나라 · 단계 사진" : "조리 기법 예시 · AI 이미지";
  return `<figure class="technique-photo"><img src="${esc(card["사진"] || example)}" alt="${esc(card["동작"] || "조리")} 기법 예시" data-fallback="${example}"><figcaption>${caption}</figcaption></figure>`;
}
function tabs() {
  return `<div class="cook-tabs" role="tablist">${[
    ["anim", "조리 장면"],
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
  const request = guideReq;
  const r = await api("/api/guide/media", "POST", { menu: guide["메뉴"], steps: guide["단계"].map((c) => c["설명"]) });
  if (request !== guideReq) return;
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
  ${card["손질"]?.length ? `<div class="how-box"><p class="sec-label">재료 손질</p><ul>${card["손질"].map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>` : ""}
  ${card["익힘 기준"] ? `<div class="how-box check">✅ <b>이렇게 확인해요</b> · ${esc(card["익힘 기준"])}</div>` : ""}
  ${card["불 세기"] && card["불 세기 권장"] ? `<p class="hint">🔥 불 세기는 원문에 없어 ${esc(card["불 세기"])}을 권장해요.</p>` : ""}
  ${card["팁"] ? `<p class="hint">${esc(card["팁"])}</p>` : ""}
  ${card["재료"].length ? `<div class="btnbar">${card["재료"].map((x) => `<span class="pill ${x["보유"] ? "" : "warn"}">${esc(x["아이콘"] + " " + x["이름"])}${x["분량(g)"] != null ? " " + fmt(x["분량(g)"]) + "g" : ""}${x["계량"] ? `(${esc(x["계량"])})` : ""}${x["보유"] ? "" : " · 미보유"}</span>`).join("")}</div>` : ""}
  ${secs ? `<div class="cook-timer"><div class="cook-ring" id="cook-ring" style="--p:${Math.round((1 - remain / secs) * 100)}"><b id="cook-clock">${mmss(remain)}</b></div><div><strong>${Math.round(secs / 60)}분 타이머</strong><p class="hint">원문에 적힌 시간이에요. 끝나면 진동과 음성으로 알려 드려요.</p></div>${btn(clock ? "일시정지" : remain === 0 ? "다시 시작" : remain < secs ? "이어서 시작" : "시작", "cookTimer", "btn alt", "timer")}</div>` : ""}
  <div class="cook-nav">${btn("이전", "cookPrev", "btn alt", "chevron-left")}${btn("읽어주기", "cookSpeak", "btn alt", "volume-2")}${last ? btn("조리 완료 기록", "cookDone", "btn", "check") : btn("다음", "cookNext", "btn", "chevron-right")}</div>
  <details><summary>전체 재료 (${guide["인분"]}인분)</summary><p>${guide["재료 합계"].map((x) => esc(x["아이콘"] + " " + x["이름"]) + (x["분량(g)"] != null ? " " + fmt(x["분량(g)"]) + "g" : "")).join(" · ")}</p><p class="hint">${esc(guide["안내"])} · ${esc(guide["출처"])} · ${esc(guide["판단 방법"])}</p></details></div>`;
}
function paint() {
  $("#sheet-body").innerHTML = cookCard();
  const photo = document.querySelector("#sheet-body .technique-photo img");
  if (photo) photo.onerror = () => {
    photo.onerror = null;
    photo.src = photo.dataset.fallback;
    photo.nextElementSibling.textContent = "조리 기법 예시 · AI 이미지";
  };
  if (tab === "social" && mediaInfo?.instagram?.ok) loadInstagram();
}
function showStep(i) {
  stopClock();
  stopVoice();
  stepAt = Math.max(0, Math.min(i, guide["단계"].length - 1));
  remain = guide["단계"][stepAt]["타이머(초)"] || 0;
  paint();
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
        `<div class="photo-row"><label class="check"><input type="checkbox" name="pick" value="${i}" ${x.confidence >= 0.4 ? "checked" : ""} aria-label="${esc(x.name)} 선택"></label>
          <div class="photo-fields"><input name="n${i}" value="${esc(x.name)}" maxlength="40" aria-label="음식 이름" required>${meal ? `<input class="grams" name="g${i}" type="number" min="1" max="3000" value="${x.grams ?? ""}" placeholder="g" aria-label="${esc(x.name)} 양(g)" required><span>g</span>` : ""}</div>
          <small>확신도 ${Math.round(x.confidence * 100)}%${x["보유"] ? " · 이미 보유" : ""}${meal ? ` · ${esc(x["근거"] || "")}${x["예상 kcal"] != null ? ` · 약 ${fmt(x["예상 kcal"])}kcal` : ""}` : ""}</small></div>`,
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
  measureGuideLot: (id) => measureLotForm(id, true),
  guideCart: async () => {
    const r = await send("장바구니담기", { servings: guide["인분"], menu: guide["메뉴"] });
    if (r) go("pantry");
  },
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
      remain = Math.max(0, Math.ceil((timerEnds - Date.now()) / 1000));
      stopClock();
      paint();
      return;
    }
    if (!remain) remain = guide["단계"][stepAt]["타이머(초)"];
    timerEnds = Date.now() + remain * 1000;
    clock = setInterval(() => {
      remain = Math.max(0, Math.ceil((timerEnds - Date.now()) / 1000));
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
  cookDone: async () => {
    stopClock();
    stopVoice();
    // 조리 모드에서 본 레시피로 기록한다(오늘 추천 메뉴가 아니라)
    if (guideReq?.recipe_id) {
      note("국내 레시피는 ‘내 식단에 담기’로 1인분 재료를 확인한 뒤 조리를 기록할 수 있어요.");
      return action.importRecipe?.(guideReq.recipe_id);
    }
    const r = await api("/api/chat", "POST", { message: "메뉴 " + guide["메뉴"], request_id: uid() });
    st = { ...r, 계획: r["현재 추천"] };
    action.cook();
    const s = $("#sheet-body input[name=servings]");
    if (s) s.value = guide["인분"];
  },
  intakeDelete: async (i) => {
    if (!confirm("이 섭취 기록을 지울까요?")) return;
    await send("섭취삭제 " + i, {}, false);
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
    const nameOf = (i) => (f.elements["n" + i]?.value || photoResult["후보"][i].name).trim();
    if (f.dataset.kind === "meal") {
      const r = await api("/api/chat", "POST", {
        message: "사진식사",
        params: { items: picks.map((i) => ({ name: nameOf(i), grams: Number(f.elements["g" + i].value), parts: nameOf(i) === photoResult["후보"][i].name ? photoResult["후보"][i].parts || [] : [] })) },
        request_id: uid(),
      });
      st = { ...r, 계획: r["현재 추천"] };
      close();
      go("journal");
      return note(r["계획"]["안내"] || "식사를 기록했어요.");
    }
    await send("입고", { name: picks.map(nameOf).join(", "), quantity: null });
    go("pantry");
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
