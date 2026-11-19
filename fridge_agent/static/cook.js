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
function stage(card) {
  // 단계 사진이 있으면 사진, 없으면 재료 아이콘이 그릇으로 들어가는 애니메이션
  if (card["사진"])
    return `<figure class="cook-photo"><img src="${esc(card["사진"])}" alt="${esc(card["순서"] + "단계 조리 사진")}" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('figure').classList.add('broken')"><figcaption>식품안전나라 조리 과정 사진</figcaption></figure>`;
  const items = card["재료"].length ? card["재료"] : [{ 아이콘: guide["대표 아이콘"], 이름: "" }];
  return `<div class="cook-stage anim-${esc(card["애니메이션"])}" role="img" aria-label="${esc(card["동작"] + " " + card["재료"].map((x) => x["이름"]).join(", "))}">
    <div class="cook-items">${items.map((x, i) => `<span style="--i:${i}">${esc(x["아이콘"])}</span>`).join("")}</div>
    <div class="cook-vessel">${vessel[card["애니메이션"]] || "🍲"}</div><div class="cook-fx" aria-hidden="true"><i></i><i></i><i></i></div></div>`;
}
function cookCard() {
  const card = guide["단계"][stepAt],
    total = guide["단계"].length,
    last = stepAt === total - 1;
  return `<div class="cook">
  <div class="cook-progress" aria-label="${stepAt + 1}/${total}단계"><i style="width:${((stepAt + 1) / total) * 100}%"></i></div>
  <p class="eyeline">${stepAt + 1} / ${total}단계 · ${esc(card["동작"])}${card["불 세기"] ? " · " + esc(card["불 세기"]) : ""}</p>
  ${stage(card)}
  <p class="cook-text">${esc(card["설명"])}</p>
  ${card["팁"] ? `<p class="hint">${esc(card["팁"])}</p>` : ""}
  ${card["재료"].length ? `<div class="btnbar">${card["재료"].map((x) => `<span class="pill ${x["보유"] ? "" : "warn"}">${esc(x["아이콘"] + " " + x["이름"])}${x["분량(g)"] != null ? " " + fmt(x["분량(g)"]) + "g" : ""}${x["보유"] ? "" : " · 미보유"}</span>`).join("")}</div>` : ""}
  ${card["타이머(초)"] ? `<div class="cook-timer"><b id="cook-clock">${mmss(remain || card["타이머(초)"])}</b>${btn(clock ? "일시정지" : "타이머 시작", "cookTimer", "btn alt", "timer")}</div>` : ""}
  <div class="cook-nav">${btn("이전", "cookPrev", "btn alt", "chevron-left")}${btn("읽어주기", "cookSpeak", "btn alt", "volume-2")}${last ? btn("조리 완료 기록", "cookDone", "btn", "check") : btn("다음", "cookNext", "btn", "chevron-right")}</div>
  <details><summary>전체 재료 (${guide["인분"]}인분)</summary><p>${guide["재료 합계"].map((x) => esc(x["아이콘"] + " " + x["이름"]) + (x["분량(g)"] != null ? " " + fmt(x["분량(g)"]) + "g" : "")).join(" · ")}</p><p class="hint">${esc(guide["안내"])} · ${esc(guide["출처"])} · ${esc(guide["판단 방법"])}</p></details></div>`;
}
function showStep(i) {
  stopClock();
  stopVoice();
  stepAt = Math.max(0, Math.min(i, guide["단계"].length - 1));
  remain = guide["단계"][stepAt]["타이머(초)"] || 0;
  $("#sheet-body").innerHTML = cookCard();
}
async function openGuide(req) {
  const servings = Number(prompt("몇 인분을 만들까요? (1~20)", "1") || 0);
  if (!servings) return;
  markWaiting("조리 단계를 준비하고 있어요…");
  try {
    guide = await api("/api/guide", "POST", { ...req, servings });
  } finally {
    document.querySelectorAll("#main [data-progress]").forEach((el) => el.remove());
  }
  sheet(guide["메뉴"] + " · 조리 모드", "");
  showStep(0);
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
  cookNext: () => showStep(stepAt + 1),
  cookPrev: () => showStep(stepAt - 1),
  cookSpeak: () => {
    const c = guide["단계"][stepAt];
    speak(`${stepAt + 1}단계. ${c["설명"]}`);
  },
  cookTimer: () => {
    if (clock) {
      stopClock();
      $("#sheet-body").innerHTML = cookCard();
      return;
    }
    clock = setInterval(() => {
      remain = Math.max(0, remain - 1);
      const el = $("#cook-clock");
      if (el) el.textContent = mmss(remain);
      if (!remain) {
        stopClock();
        navigator.vibrate?.([300, 120, 300]);
        speak("타이머가 끝났어요. 다음 단계를 확인하세요.");
        if (el) $("#sheet-body").innerHTML = cookCard();
      }
    }, 1000);
    $("#sheet-body").innerHTML = cookCard();
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
});
