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

let wkCustom = false;
async function loadWorkout(force = false, routineId = null) {
  if (wk && !force) return wk;
  if (wkLoading) return wk;
  wkLoading = true;
  try {
    wk = await api("/api/workout/guide", "POST", routineId ? { routine_id: routineId } : {});
    wkCustom = !!routineId;
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
  return `<article class="ex-card"><div class="ex-fig">${demo(s, { small: true, speed: 1.2 })}</div><div class="ex-info"><span class="ex-no">${i}</span><strong>${esc(s.name)}</strong><small>${s.kind === "exercise" ? (s.mode === "reps" ? `${s.reps}회 × ${s.sets}세트 · 휴식 ${s.rest}초 · 템포 ${s.tempo.join("-")}` : `${s.seconds}초 ${s.mode === "hold" ? "버티기" : "동안"} × ${s.sets}세트 · 휴식 ${s.rest}초`) : (s.kind === "warmup" ? "준비 운동 · " : "마무리 · ") + secText(s.seconds)}</small><div class="btnbar">${s.muscles.map((m) => pill(m)).join("")}</div>
    <details><summary>하는 방법</summary><ol class="step-list">${s.how.map((h) => `<li>${esc(h)}</li>`).join("")}</ol>${s.mistakes?.length ? `<p class="hint warn-text">이건 피하세요 · ${s.mistakes.map(esc).join(" · ")}</p>` : ""}<p class="hint">호흡 · ${esc(s.breath)}</p>${s.easier ? `<p class="hint">쉽게 · ${esc(s.easier)} / 어렵게 · ${esc(s.harder)}</p>` : ""}</details></div></article>`;
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
      <h2>${esc(r.move || r.summary)}</h2><p>${main.length ? `준비 운동 → 동작 ${main.length}개 × ${main[0].sets}세트 → 마무리 스트레칭 · 약 ${Math.round((g["총 시간(초)"] || 0) / 60)}분` : esc(r.summary)}</p>
      <div class="actions">${steps.length ? btn("운동 시작", "wkStart", "btn light", "timer") : ""}${btn("조건 변경", "settings", "btn ghost", "sliders-horizontal")}</div></div>
      <div class="wk-hero-fig">${first ? demo(first) : figureSVG("walk", null, {})}</div></section>
    <section class="card">${section("오늘 루틴")}${steps.length ? `<div class="ex-list">${steps.map((s, i) => exerciseCard(s, i + 1)).join("")}</div>` : `<p class="muted">${g ? esc(g["안내"] || "") : "루틴을 불러오는 중…"}</p>`}<p class="footnote">${esc(g?.["주의"] || "")}</p></section></div>
    <div class="stack"><section class="card">${section("다른 선택지")}${(g?.options || []).map((o) => `<article class="opt"><div><strong>${esc(o.title)}</strong><small>${esc(o.why)}</small><small class="muted">${esc(o.summary)}</small></div>${btn("이걸로", "wkApply", "chip", "", JSON.stringify(o.apply))}</article>`).join("") || '<p class="muted">불러오는 중…</p>'}
      <p class="sec-label">부위 바로 바꾸기</p><div class="chips">${(g?.bodies || []).map((b) => btn(b, "wkApply", "chip " + (b === r.body ? "on" : ""), "", JSON.stringify({ body: b }))).join("")}</div>
      <p class="sec-label">강도</p><div class="chips">${(g?.levels || []).map((l) => btn(l, "wkApply", "chip " + (l === r.level ? "on" : ""), "", JSON.stringify({ level: l }))).join("")}</div></section>
    <section class="card">${section("나만의 루틴")}${(g?.["내 루틴"] || []).map((x) => `<article class="opt"><div><strong>${esc(x.name)}</strong><small>${x.items.map((i) => `${esc(i.name)} ${i.amount}${i.mode === "reps" ? "회" : "초"}×${i.sets}`).join(" · ")}</small></div><div class="btnbar">${btn("시작", "wkStartCustom", "chip", "timer", x.id)}${btn("삭제", "wkDeleteCustom", "linkbtn", "", x.id)}</div></article>`).join("") || '<p class="muted">자주 하는 동작을 골라 나만의 루틴으로 저장해 보세요.</p>'}<div class="actions">${btn("새 루틴 만들기", "wkBuilder", "btn alt", "plus")}</div></section>
    <section class="card">${section("최근 운동")}${logs.length ? logs.slice(-4).reverse().map((x) => `<div class="list-line"><strong>${esc(x.body)} · ${x.minutes}분</strong><small>${esc(x.effort)} · ${x.day}</small></div>`).join("") : '<p class="muted">완료 후 남긴 체감 난이도를 다음 루틴에 반영해요.</p>'}</section>
    <section class="card">${section("근처 헬스장")}${sourceForm("헬스장", "동네나 역 이름", "카카오맵으로 찾기")}</section>
    <section class="card"><details><summary>운동 자료와 출처</summary>${catalog.exercises.map((x) => `<div class="list-line"><div>${a(x.title, x.url)}<small>${esc(x.authors.join(", "))} · ${a("이용 조건", x.license)}</small></div></div>`).join("")}</details></section></div></div>`
  );
};

// ── 운동 모드: 트레이너처럼 ─────────────────────────
// 설명(intro) → 세트 진행(work: 템포에 맞춘 횟수 세기·자세 교정 멘트 / 버티기 타이머) → 휴식(rest)
// → 동작이 끝나면 "어땠어요?"(feedback)로 다음 동작 강도 조정 → 끝(done)
let wkRep = 0,
  wkBeat = 0,
  wkBeatLeft = 0,
  wkCue = "",
  wkAdj = { reps: 0, hold: 0, rest: 0 },
  wkFeel = [],
  wkSetsDone = 0,
  wkBegan = 0;
const UP_FIRST = new Set(["curl", "raise", "row", "prone", "wallslide", "birddog", "deadbug", "shouldertap", "breathe"]);
const beatWords = (s) => (UP_FIRST.has(s.motion) ? ["올려요", "멈춰요", "내려요"] : ["내려가요", "멈춰요", "올라와요"]);
const KOR = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉", "열", "열하나", "열둘", "열셋", "열넷", "열다섯", "열여섯", "열일곱", "열여덟", "열아홉", "스물"];
function wkStep() {
  return wk["단계"][wkAt];
}
function targetReps(s) {
  return Math.max(5, (s.reps || 10) + wkAdj.reps);
}
function targetHold(s) {
  return s.mode === "hold" || (s.mode === "time" && s.kind === "exercise") ? Math.max(10, s.seconds + wkAdj.hold) : s.seconds;
}
function restOf(s) {
  return Math.max(15, s.rest + wkAdj.rest);
}
function say(text) {
  wkCue = text;
  speak(text);
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
function amountText(s) {
  if (s.mode === "reps") return `${targetReps(s)}회 × ${s.sets}세트 · 휴식 ${restOf(s)}초`;
  if (s.mode === "hold") return `${targetHold(s)}초 버티기 × ${s.sets}세트 · 휴식 ${restOf(s)}초`;
  if (s.kind === "exercise") return `${targetHold(s)}초 동안 × ${s.sets}세트 · 휴식 ${restOf(s)}초`;
  return secText(s.seconds);
}
function counterBlock(s) {
  if (wkPhase === "work" && s.mode === "reps") {
    const words = beatWords(s);
    return `<div class="rep-box"><div class="rep-count"><b id="wk-rep">${wkRep}</b><span>/ ${targetReps(s)}회</span></div>
      <div class="beats">${[0, 1, 2].map((k) => `<span class="${k === wkBeat ? "on" : ""}">${words[k]} ${s.tempo[k]}초</span>`).join("")}</div></div>`;
  }
  const total = wkPhase === "rest" ? restOf(s) : targetHold(s);
  const pct = Math.round((1 - wkLeft / Math.max(1, total)) * 100);
  return `<div class="cook-ring big" id="wk-ring" style="--p:${pct}"><b id="wk-clock">${mmss(wkLeft)}</b></div>`;
}
function introPanel(s) {
  const adjusted = s.kind === "exercise" && (wkAdj.reps || wkAdj.hold || wkAdj.rest) ? " (앞 동작 체크를 반영해 조정했어요)" : "";
  return `<div class="coach-say">🗣 ${esc(s.intro || s.name)}</div>
    <p class="prescribe">오늘 처방 · <b>${esc(amountText(s))}</b>${adjusted}</p>
    <div class="wk-points"><p class="sec-label">자세 포인트</p><ol class="step-list">${s.how.map((h) => `<li>${esc(h)}</li>`).join("")}</ol>
    ${s.mistakes?.length ? `<p class="sec-label">이건 피하세요</p><ul class="mistakes">${s.mistakes.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : ""}
    <p class="hint">호흡 · ${esc(s.breath)}</p><p class="hint warn-text">주의 · ${esc(s.caution)}</p>
    ${s.easier || s.harder ? `<div class="variants">${s.easier ? `<span class="pill">쉽게 · ${esc(s.easier)}</span>` : ""}${s.harder ? `<span class="pill">어렵게 · ${esc(s.harder)}</span>` : ""}</div>` : ""}</div>`;
}
function wkCard() {
  const steps = wk["단계"],
    s = wkStep();
  if (!s || wkPhase === "done") {
    const mins = Math.max(1, Math.round((Date.now() - wkBegan) / 60000));
    return `<div class="wk wk-done"><div class="wk-trophy">🎉</div><h2>오늘 운동 끝! 수고했어요</h2><p>${esc(wk["루틴"].summary)}</p>
      <div class="facts"><div class="fact"><small>완료 세트</small><b>${wkSetsDone}<span>세트</span></b></div><div class="fact"><small>운동 시간</small><b>${mins}<span>분</span></b></div></div>
      ${wkFeel.length ? `<p class="hint">동작별 느낌 · ${wkFeel.map((f) => `${esc(f.name)} ${esc(f.feel)}`).join(" · ")}</p>` : ""}
      <div class="cta">${btn("완료 기록하기", "wkFinish", "btn", "check")}${btn("닫기", "close", "btn alt")}</div><p class="footnote">${esc(wk["주의"])}</p></div>`;
  }
  const full = dialog.classList.contains("cook-full");
  const all = steps.reduce((t, x) => t + x.sets, 0);
  const badge = wkPhase === "intro" ? "설명" : wkPhase === "rest" ? "휴식" : wkPhase === "feedback" ? "체크" : s.kind === "exercise" ? `${wkSet} / ${s.sets}세트` : phaseName(s);
  let body = "";
  if (wkPhase === "intro") body = introPanel(s) + `<div class="cook-nav">${btn("이전", "wkPrev", "btn alt", "chevron-left")}${btn("준비됐어요, 시작", "wkBegin", "btn", "timer")}${btn("건너뛰기", "wkSkip", "btn alt", "chevron-right")}</div>`;
  else if (wkPhase === "feedback")
    body = `<div class="coach-say">🗣 ${esc(s.name)} 끝! 어땠어요? 다음 동작 강도를 맞춰 드릴게요.</div><div class="feel">${[["쉬움", "😌", "다음 동작 +2회"], ["적당함", "🙂", "그대로"], ["어려움", "😮‍💨", "다음 동작 −2회, 휴식 +15초"]].map(([k, e, d]) => `<button type="button" class="feel-btn" data-do="wkFeel" data-arg="${k}"><span>${e}</span><b>${k}</b><small>${d}</small></button>`).join("")}</div>`;
  else
    body = `<div class="wk-now">${counterBlock(s)}<div><h3>${esc(wkPhase === "rest" ? `쉬어요 · 다음 ${wkSet + 1}세트` : s.name)}</h3><p class="muted">${esc(amountText(s))}</p></div></div>
      <div class="coach-say live" aria-live="polite">🗣 ${esc(wkCue || (wkPhase === "rest" ? "물 한 모금 마시고 호흡을 고르세요." : (s.cues || [])[0] || ""))}</div>
      <div class="cook-nav">${btn("이전 동작", "wkPrev", "btn alt", "chevron-left")}${btn(wkTimer ? "일시정지" : "계속", "wkToggle", "btn", "timer")}${btn(wkPhase === "rest" ? "휴식 건너뛰기" : "세트 끝내기", "wkSkipSet", "btn alt", "chevron-right")}</div>`;
  return `<div class="wk">
    <div class="cook-progress"><i style="width:${(wkSetsDone / all) * 100}%"></i></div>
    <div class="cook-head"><p class="eyeline">${wkAt + 1} / ${steps.length} · ${phaseName(s)}</p>${btn(full ? "작게 보기" : "크게 보기", "wkFull", "linkbtn", "panels-top-left")}</div>
    <div class="cook-tabs">${[["move", "동작"], ["video", "자세 영상"]].map(([k, n]) => `<button type="button" class="chip ${wkTab === k ? "on" : ""}" data-do="wkTab" data-arg="${k}">${n}</button>`).join("")}</div>
    <div class="wk-stage ${wkPhase}">${wkTab === "move" ? (wkPhase === "rest" ? figureSVG("breathe", null, { label: "휴식", speed: 1.4 }) : demo(s)) : wkVideoPane(s)}<div class="wk-badge">${badge}</div></div>
    ${body}</div>`;
}
function wkPaint() {
  $("#sheet-body").innerHTML = wkCard();
}
function wkStop() {
  clearInterval(wkTimer);
  wkTimer = 0;
}
function wkRun() {
  wkStop();
  wkTimer = setInterval(wkTick, 1000);
}
function wkIntro(i) {
  wkStop();
  wkAt = Math.max(0, i);
  wkSet = 1;
  wkCue = "";
  const s = wkStep();
  if (!s) {
    wkPhase = "done";
    say("오늘 운동을 모두 마쳤어요. 정말 수고했어요!");
    return wkPaint();
  }
  wkPhase = "intro";
  speak(s.intro || s.name);
  wkPaint();
}
function wkBeginSet() {
  const s = wkStep();
  wkPhase = "work";
  wkRep = 0;
  wkBeat = 0;
  wkBeatLeft = s.tempo?.[0] || 2;
  wkLeft = targetHold(s);
  say(s.kind === "exercise" ? (s.mode === "reps" ? `${wkSet}세트 시작! ${beatWords(s)[0]}` : `${wkSet}세트 시작! ${targetHold(s)}초 동안 ${s.mode === "hold" ? "버텨요" : "이어가요"}.`) : `${s.name} 시작!`);
  wkRun();
  wkPaint();
}
function afterSet() {
  const s = wkStep();
  wkSetsDone += 1;
  if (wkSet < s.sets) {
    wkPhase = "rest";
    wkLeft = restOf(s);
    say(`잘했어요! ${wkLeft}초 쉬어요.`);
    navigator.vibrate?.(200);
    return wkPaint();
  }
  wkStop();
  if (s.kind === "exercise") {
    wkPhase = "feedback";
    say("좋아요! 어땠어요?");
    return wkPaint();
  }
  wkIntro(wkAt + 1);
}
function updateLive() {
  const s = wkStep();
  const rep = $("#wk-rep");
  if (rep) {
    rep.textContent = wkRep;
    document.querySelectorAll(".beats span").forEach((el, k) => el.classList.toggle("on", k === wkBeat));
  }
  const c = $("#wk-clock"),
    ring = $("#wk-ring");
  if (c) {
    const total = wkPhase === "rest" ? restOf(s) : targetHold(s);
    c.textContent = mmss(wkLeft);
    ring?.style.setProperty("--p", Math.round((1 - wkLeft / Math.max(1, total)) * 100));
  }
  const cue = $(".coach-say.live");
  if (cue && wkCue) cue.textContent = "🗣 " + wkCue;
}
function wkTick() {
  const s = wkStep();
  if (!s) return wkStop();
  if (wkPhase === "rest") {
    wkLeft -= 1;
    if (wkLeft === 5) say("5초 뒤에 다음 세트 시작해요.");
    if (wkLeft <= 0) {
      wkSet += 1;
      return wkBeginSet();
    }
    return updateLive();
  }
  if (wkPhase !== "work") return;
  if (s.mode === "reps") {
    wkBeatLeft -= 1;
    if (wkBeatLeft > 0) return updateLive();
    wkBeat += 1;
    if (wkBeat > 2) {
      wkRep += 1;
      wkBeat = 0;
      const goal = targetReps(s);
      if (wkRep >= goal) {
        speak(KOR[wkRep] || String(wkRep));
        return afterSet();
      }
      const cues = s.cues || [];
      if (goal - wkRep === 2) say(`${KOR[wkRep] || wkRep}! 마지막 두 개, 힘내요!`);
      else if (wkRep % 3 === 0 && cues.length) say(`${KOR[wkRep] || wkRep}. ${cues[(wkRep / 3) % cues.length]}`);
      else speak(KOR[wkRep] || String(wkRep));
    }
    wkBeatLeft = s.tempo[wkBeat] || 1;
    return updateLive();
  }
  wkLeft -= 1; // 버티기·시간형
  const elapsed = targetHold(s) - wkLeft;
  if (wkLeft === 3) speak("셋, 둘, 하나");
  else if (elapsed > 0 && elapsed % 10 === 0 && wkLeft > 3 && (s.cues || []).length) say(s.cues[(elapsed / 10) % s.cues.length]);
  if (wkLeft <= 0) return afterSet();
  updateLive();
}
async function wkOpen(routineId = null) {
  await loadWorkout(true, routineId);
  if (!wk["단계"].length) return note(wk["안내"] || "운동 시간을 5분 이상으로 설정해 주세요.");
  wkTab = "move";
  wkAdj = { reps: 0, hold: 0, rest: 0 };
  wkFeel = [];
  wkSetsDone = 0;
  wkBegan = Date.now();
  sheet(wk["루틴"].body + " 운동 · 트레이너 모드", "");
  wkIntro(0);
}
Object.assign(action, {
  wkStart: () => wkOpen(),
  wkStartCustom: (id) => wkOpen(id),
  wkDeleteCustom: async (id) => {
    if (!confirm("이 루틴을 삭제할까요?")) return;
    await api("/api/chat", "POST", { message: "내루틴삭제 " + id, request_id: uid() });
    await loadWorkout(true);
    render();
  },
  wkBuilder: () => {
    const list = wk?.["운동 목록"] || {};
    sheet(
      "나만의 루틴 만들기",
      `<form class="form" data-form="wkSave">${field("루틴 이름", "name", "text", "", "required maxlength=30 placeholder='예: 출근 전 15분'")}
      <p class="hint">동작을 고르고 세트·횟수(버티기는 초)·휴식을 정하세요. 최대 10개.</p>
      ${Object.entries(list).map(([body, moves]) => `<details ${body === st["운동 계획"].body ? "open" : ""}><summary>${esc(body)}</summary>${moves.map((m) => `<div class="build-row"><label class="check"><input type="checkbox" name="pick" value="${esc(m.name)}" data-mode="${m.mode}"> ${esc(m.name)}</label><input type="number" name="sets:${esc(m.name)}" value="3" min="1" max="10" aria-label="세트"><span>세트</span><input type="number" name="amount:${esc(m.name)}" value="${m.mode === "reps" ? 12 : 30}" min="${m.mode === "reps" ? 3 : 10}" max="${m.mode === "reps" ? 50 : 180}" aria-label="${m.mode === "reps" ? "횟수" : "초"}"><span>${m.mode === "reps" ? "회" : "초"}</span><input type="number" name="rest:${esc(m.name)}" value="45" min="15" max="180" aria-label="휴식"><span>휴식</span></div>`).join("")}</details>`).join("")}
      <button class="btn" type="submit">${ic("check")}루틴 저장</button></form>`,
    );
  },
  wkBegin: () => wkBeginSet(),
  wkToggle: () => {
    if (wkTimer) {
      wkStop();
      say("잠시 멈췄어요. 준비되면 계속을 눌러요.");
      return wkPaint();
    }
    wkRun();
    wkPaint();
  },
  wkSkipSet: () => {
    if (wkPhase === "rest") {
      wkSet += 1;
      return wkBeginSet();
    }
    afterSet();
  },
  wkSkip: () => wkIntro(wkAt + 1),
  wkPrev: () => wkIntro(wkAt - 1),
  wkFeel: (feel) => {
    const s = wkStep();
    wkFeel.push({ name: s.name, feel });
    if (feel === "쉬움") wkAdj = { ...wkAdj, reps: wkAdj.reps + 2, hold: wkAdj.hold + 10 };
    if (feel === "어려움") wkAdj = { reps: wkAdj.reps - 2, hold: wkAdj.hold - 10, rest: wkAdj.rest + 15 };
    speak(feel === "쉬움" ? "좋아요, 다음 동작은 조금 더 해 볼게요." : feel === "어려움" ? "괜찮아요, 다음 동작은 조금 줄이고 더 쉬어요." : "좋아요, 이대로 갈게요.");
    wkIntro(wkAt + 1);
  },
  wkTab: (k) => {
    wkTab = k;
    wkPaint();
  },
  wkFull: () => {
    dialog.classList.toggle("cook-full");
    wkPaint();
  },
  wkFinish: () => {
    const minutes = Math.max(1, Math.round((Date.now() - wkBegan) / 60000));
    const effort = wkFeel.some((f) => f.feel === "어려움") ? "어려움" : wkFeel.length && wkFeel.every((f) => f.feel === "쉬움") ? "쉬움" : "적당함";
    sheet(
      "운동 완료 기록",
      form("finish", `${field("운동 시간(분)", "minutes", "number", minutes, "min=1 max=240 required")}${select("체감 난이도", "effort", ["쉬움", "적당함", "어려움"], effort)}<p class="hint">동작별 체크를 반영해 골라 두었어요. "어려움"이면 다음 루틴을 한 단계 쉽게 짜요.</p>`, "기록하기"),
    );
  },
  wkApply: async (raw) => {
    const params = JSON.parse(raw),
      cur = st["운동 계획"];
    if (Object.entries(params).every(([k, v]) => (k === "exercise_minutes" ? cur.minutes : cur[k]) === v)) return note("이미 선택된 조건이에요.");
    const r = await api("/api/chat", "POST", { message: "설정", params, request_id: uid() });
    st = { ...r, 계획: r["현재 추천"] };
    await loadWorkout(true);
    render();
    note("루틴을 바꿨어요.");
  },
});
dialog.addEventListener("close", () => {
  wkStop();
  if (wkCustom) {
    wk = null; // 나만의 루틴을 마치면 운동 탭은 오늘 루틴으로 돌아간다
    wkCustom = false;
    if (route() === "workout") render();
  }
});
Object.assign(forms, {
  wkSave: async (v, f) => {
    const picks = [...f.querySelectorAll("input[name=pick]:checked")].map((x) => x.value);
    if (!picks.length) throw Error("동작을 하나 이상 고르세요.");
    const val = (k) => Number(f.elements[k]?.value);
    const items = picks.map((n) => ({ name: n, sets: val("sets:" + n), amount: val("amount:" + n), rest: val("rest:" + n) }));
    await api("/api/chat", "POST", { message: "내루틴저장", params: { name: v.name, items }, request_id: uid() });
    close();
    await loadWorkout(true);
    render();
    note("나만의 루틴을 저장했어요.");
  },
});
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
