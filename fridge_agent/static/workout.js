"use strict";
// 운동 화면과 운동 모드: 요리 조리 모드처럼 동작 애니메이션 · 하는 방법 · 세트/휴식 타이머 · 음성 · 자세 영상
let wk = null, // /api/workout/guide 응답
  wkAt = 0,
  wkSet = 1,
  wkPhase = "work",
  wkLeft = 0,
  wkTimer = 0,
  wkTab = "move",
  wkMedia = {},
  wkLoading = false;

async function loadWorkout(force = false) {
  if (wk && !force) return wk;
  if (wkLoading) return wk;
  wkLoading = true;
  try {
    wk = await api("/api/workout/guide", "POST", {});
  } finally {
    wkLoading = false;
  }
  return wk;
}
function photoDemo(s, small = false) {
  // 실제 사람이 시작 자세 ↔ 끝 자세를 하는 사진 2장을 번갈아 보여 준다
  return `<figure class="photo-demo ${small ? "small" : ""}"><img src="${esc(s.photos[0])}" alt="${esc(s.name)} 시작 자세" loading="lazy"><img src="${esc(s.photos[1])}" alt="${esc(s.name)} 끝 자세" loading="lazy">${small ? "" : `<span class="pd-label a">시작 자세</span><span class="pd-label b">끝 자세</span><figcaption>${esc(s.credit || "")}${s.photo_note ? " · " + esc(s.photo_note) : ""}</figcaption>`}</figure>`;
}
function demo(s, opts = {}) {
  return s.photos?.length ? photoDemo(s, opts.small) : figureSVG(s.motion, s.prop, { label: s.name, ...opts });
}
const secText = (s) => (s >= 60 ? `${Math.floor(s / 60)}분${s % 60 ? " " + (s % 60) + "초" : ""}` : `${s}초`);
const phaseName = (step) => (step.kind === "warmup" ? "준비 운동" : step.kind === "cooldown" ? "마무리" : "운동");

function exerciseCard(s, i) {
  return `<article class="ex-card"><div class="ex-fig">${demo(s, { small: true, speed: 1.2 })}</div><div class="ex-info"><span class="ex-no">${i}</span><strong>${esc(s.name)}</strong><small>${s.kind === "exercise" ? `${s.seconds}초 운동 + ${s.rest}초 휴식 × ${s.sets}세트` : secText(s.seconds)}</small><div class="btnbar">${s.muscles.map((m) => pill(m)).join("")}</div>
    <details><summary>하는 방법</summary><ol class="step-list">${s.how.map((h) => `<li>${esc(h)}</li>`).join("")}</ol><p class="hint">호흡 · ${esc(s.breath)}</p><p class="hint warn-text">주의 · ${esc(s.caution)}</p></details></div></article>`;
}

workoutView = function () {
  const r = st["운동 계획"],
    logs = st["운동 기록"] || [];
  const g = wk;
  const steps = g?.["단계"] || [];
  const main = steps.filter((s) => s.kind === "exercise");
  const first = main[0] || steps[0];
  if (!g) setTimeout(() => loadWorkout().then(() => route() === "workout" && render()), 0);
  return (
    heading("workout", "부위·강도·시간에 맞춘 오늘 루틴을 동작 애니메이션과 함께 따라 해요.") +
    `<div class="panelgrid wideleft"><div class="stack">
    <section class="wk-hero"><div class="wk-hero-copy"><div class="btnbar">${pill((r.level || "초보") + " · " + r.body)}${pill("휴식 포함 " + r.minutes + "분")}</div>
      <h2>${esc(r.move || r.summary)}</h2><p>${main.length ? `준비 1분 · 동작 ${main.length}개 × ${main[0].sets}세트 · 마무리 1분` : esc(r.summary)}</p>
      <div class="actions">${steps.length ? btn("운동 시작", "wkStart", "btn light", "timer") : ""}${btn("조건 변경", "settings", "btn ghost", "sliders-horizontal")}</div></div>
      <div class="wk-hero-fig">${first ? demo(first) : figureSVG("walk", null, {})}</div></section>
    <section class="card">${section("오늘 루틴")}${steps.length ? `<div class="ex-list">${steps.map((s, i) => exerciseCard(s, i + 1)).join("")}</div>` : `<p class="muted">${g ? esc(g["안내"] || "") : "루틴을 불러오는 중…"}</p>`}<p class="footnote">${esc(g?.["주의"] || "")}</p></section></div>
    <div class="stack"><section class="card">${section("다른 선택지")}${(g?.options || []).map((o) => `<article class="opt"><div><strong>${esc(o.title)}</strong><small>${esc(o.why)}</small><small class="muted">${esc(o.summary)}</small></div>${btn("이걸로", "wkApply", "chip", "", JSON.stringify(o.apply))}</article>`).join("") || '<p class="muted">불러오는 중…</p>'}
      <p class="sec-label">부위 바로 바꾸기</p><div class="chips">${(g?.bodies || []).map((b) => btn(b, "wkApply", "chip " + (b === r.body ? "on" : ""), "", JSON.stringify({ body: b }))).join("")}</div>
      <p class="sec-label">강도</p><div class="chips">${(g?.levels || []).map((l) => btn(l, "wkApply", "chip " + (l === r.level ? "on" : ""), "", JSON.stringify({ level: l }))).join("")}</div></section>
    <section class="card">${section("최근 운동")}${logs.length ? logs.slice(-4).reverse().map((x) => `<div class="list-line"><strong>${esc(x.body)} · ${x.minutes}분</strong><small>${esc(x.effort)} · ${x.day}</small></div>`).join("") : '<p class="muted">완료 후 남긴 체감 난이도를 다음 루틴에 반영해요.</p>'}</section>
    <section class="card">${section("근처 헬스장")}${sourceForm("헬스장", "동네나 역 이름", "카카오맵으로 찾기")}</section>
    <section class="card"><details><summary>운동 자료와 출처</summary>${catalog.exercises.map((x) => `<div class="list-line"><div>${a(x.title, x.url)}<small>${esc(x.authors.join(", "))} · ${a("이용 조건", x.license)}</small></div></div>`).join("")}</details></section></div></div>`
  );
};

// ── 운동 모드 플레이어 ───────────────────────────────
function wkStep() {
  return wk["단계"][wkAt];
}
function wkVideoPane(s) {
  const info = wkMedia[s.name];
  if (info === undefined) {
    wkMedia[s.name] = null;
    api("/api/workout/media", "POST", { name: s.name })
      .then((r) => (wkMedia[s.name] = r))
      .catch(() => delete wkMedia[s.name])
      .finally(() => dialog.open && $("#sheet-body .wk") && wkPaint());
    return '<p class="hint" role="status">자세 영상을 찾고 있어요…</p>';
  }
  if (info === null) return '<p class="hint" role="status">자세 영상을 찾고 있어요…</p>';
  const yt = info.youtube;
  return (yt.ok && yt.data.length ? ytFrame(yt.data[0]) + `<p class="footnote">${esc(yt.data[0].title)} · ${esc(yt.data[0].channel)}</p>` : `<p class="hint">YouTube · ${esc(errors[yt.error] || "영상을 찾지 못했어요.")} ${a("YouTube에서 찾기", info["직접 검색"].YouTube)}</p>`) + linkForm(s.name);
}
function wkCard() {
  const steps = wk["단계"],
    s = wkStep();
  if (!s)
    return `<div class="wk wk-done"><div class="wk-trophy">🎉</div><h2>오늘 운동을 마쳤어요!</h2><p>${esc(wk["루틴"].summary)}</p><div class="cta">${btn("완료 기록하기", "wkFinish", "btn", "check")}${btn("닫기", "close", "btn alt")}</div><p class="footnote">${esc(wk["주의"])}</p></div>`;
  const cur = wkPhase === "rest" ? s.rest : s.seconds;
  const pct = Math.round((1 - wkLeft / Math.max(1, cur)) * 100);
  const full = dialog.classList.contains("cook-full");
  const done = steps.slice(0, wkAt).reduce((t, x) => t + x.sets, 0) + (wkSet - 1);
  const all = steps.reduce((t, x) => t + x.sets, 0);
  return `<div class="wk">
    <div class="cook-progress"><i style="width:${(done / all) * 100}%"></i></div>
    <div class="cook-head"><p class="eyeline">${wkAt + 1} / ${steps.length} · ${phaseName(s)}</p>${btn(full ? "작게 보기" : "크게 보기", "wkFull", "linkbtn", "panels-top-left")}</div>
    <div class="cook-tabs">${[["move", "동작"], ["video", "자세 영상"]].map(([k, n]) => `<button type="button" class="chip ${wkTab === k ? "on" : ""}" data-do="wkTab" data-arg="${k}">${n}</button>`).join("")}</div>
    <div class="wk-stage ${wkPhase}">${wkTab === "move" ? (wkPhase === "rest" ? figureSVG("breathe", null, { label: "휴식", speed: 1.4 }) : demo(s)) : wkVideoPane(s)}
      <div class="wk-badge">${wkPhase === "rest" ? "휴식" : s.kind === "exercise" ? `${wkSet} / ${s.sets}세트` : phaseName(s)}</div></div>
    <div class="wk-now"><div class="cook-ring big" id="wk-ring" style="--p:${pct}"><b id="wk-clock">${mmss(wkLeft)}</b></div><div><h3>${esc(wkPhase === "rest" ? "쉬어요 · 다음: " + (wkSet < s.sets ? s.name : steps[wkAt + 1]?.name || "마무리") : s.name)}</h3><p class="muted">${s.kind === "exercise" ? `${s.seconds}초 운동 + ${s.rest}초 휴식` : secText(s.seconds)} · ${s.muscles.join(" · ")}</p></div></div>
    <ol class="step-list">${s.how.map((h) => `<li>${esc(h)}</li>`).join("")}</ol>
    <p class="hint">호흡 · ${esc(s.breath)}</p><p class="hint warn-text">주의 · ${esc(s.caution)}</p>
    <div class="cook-nav">${btn("이전", "wkPrev", "btn alt", "chevron-left")}${btn(wkTimer ? "일시정지" : "시작", "wkToggle", "btn", "timer")}${btn("건너뛰기", "wkNext", "btn alt", "chevron-right")}</div></div>`;
}
function wkPaint() {
  $("#sheet-body").innerHTML = wkCard();
}
function wkStop() {
  clearInterval(wkTimer);
  wkTimer = 0;
}
function wkGo(i) {
  wkStop();
  wkAt = Math.max(0, Math.min(i, wk["단계"].length));
  wkSet = 1;
  wkPhase = "work";
  wkLeft = wk["단계"][wkAt]?.seconds || 0;
  wkPaint();
}
function wkAdvance() {
  const s = wkStep();
  if (wkPhase === "work" && s.rest > 0) {
    wkPhase = "rest";
    wkLeft = s.rest;
    speak("휴식");
  } else if (wkSet < s.sets) {
    wkSet += 1;
    wkPhase = "work";
    wkLeft = s.seconds;
    speak(`${wkSet}세트 시작`);
  } else {
    wkAt += 1;
    wkSet = 1;
    wkPhase = "work";
    const n = wk["단계"][wkAt];
    if (!n) {
      wkStop();
      speak("오늘 운동을 마쳤어요. 수고했어요.");
      return wkPaint();
    }
    wkLeft = n.seconds;
    speak(`다음 동작, ${n.name}`);
  }
  navigator.vibrate?.(200);
  wkPaint();
}
function wkTick() {
  wkLeft = Math.max(0, wkLeft - 1);
  const c = $("#wk-clock"),
    ring = $("#wk-ring"),
    s = wkStep();
  if (s) {
    const cur = wkPhase === "rest" ? s.rest : s.seconds;
    if (c) c.textContent = mmss(wkLeft);
    if (ring) ring.style.setProperty("--p", Math.round((1 - wkLeft / Math.max(1, cur)) * 100));
    if (wkLeft === 3) speak("3, 2, 1");
  }
  if (!wkLeft) wkAdvance();
}
async function wkOpen() {
  await loadWorkout(true);
  if (!wk["단계"].length) return note(wk["안내"] || "운동 시간을 5분 이상으로 설정해 주세요.");
  wkTab = "move";
  sheet(wk["루틴"].body + " 운동 모드", "");
  wkGo(0);
}
Object.assign(action, {
  wkStart: () => wkOpen(),
  wkToggle: () => {
    if (wkTimer) {
      wkStop();
      return wkPaint();
    }
    if (!wkLeft) wkLeft = wkStep()?.seconds || 0;
    speak(wkPhase === "rest" ? "휴식" : `${wkStep().name} 시작`);
    wkTimer = setInterval(wkTick, 1000);
    wkPaint();
  },
  wkNext: () => {
    wkStop();
    wkPhase = "rest";
    wkSet = wkStep()?.sets || 1;
    wkAdvance();
  },
  wkPrev: () => wkGo(wkAt - 1),
  wkTab: (k) => {
    wkTab = k;
    wkPaint();
  },
  wkFull: () => {
    dialog.classList.toggle("cook-full");
    wkPaint();
  },
  wkFinish: () => {
    const minutes = Math.max(1, Math.round((wk["총 시간(초)"] || 600) / 60));
    sheet(
      "운동 완료 기록",
      form("finish", `${field("운동 시간(분)", "minutes", "number", minutes, "min=1 max=240 required")}${select("체감 난이도", "effort", ["쉬움", "적당함", "어려움"], "적당함")}<p class="hint">"어려움"을 고르면 다음 루틴 강도를 한 단계 낮춰요.</p>`, "기록하기"),
    );
  },
  wkApply: async (raw) => {
    const r = await api("/api/chat", "POST", { message: "설정", params: JSON.parse(raw), request_id: uid() });
    st = { ...r, 계획: r["현재 추천"] };
    await loadWorkout(true);
    render();
    note("루틴을 바꿨어요.");
  },
});
dialog.addEventListener("close", wkStop);
const _renderWk = render;
let wkKey = "";
render = function () {
  // 설정(부위·강도·시간)이 바뀌었을 때만 한 번 다시 받는다. 같은 조건으로 반복 요청하지 않는다.
  const r = st?.["운동 계획"];
  const key = r ? [r.body, r.level, r.minutes].join("|") : "";
  if (route() === "workout" && wk && key && key !== wkKey) {
    wk = null;
    wkKey = key;
  }
  if (!wkKey) wkKey = key;
  _renderWk();
};
