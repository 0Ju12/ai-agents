"use strict";
const $ = (sel) => document.querySelector(sel);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const ic = (name) =>
  `<svg class="ic" aria-hidden="true"><use href="/static/icons.svg#i-${esc(name)}"></use></svg>`;
const btn = (label, action, style = "btn", icon = "", arg = "") =>
  `<button type="button" class="${style}" data-do="${action}" data-arg="${esc(arg)}">${icon ? ic(icon) : ""}${esc(label)}</button>`;
const a = (label, url) =>
  /^https?:\/\//i.test(url || "")
    ? `<a href="${esc(url)}" rel="noopener noreferrer" class="textlink">${esc(label)} ↗</a>`
    : esc(label);
const pill = (s, w = false) => `<span class="pill ${w ? "warn" : ""}">${esc(s)}</span>`;
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("ko-KR", { maximumFractionDigits: 1 }));
const opts = (values, selected) =>
  values.map((v) => `<option ${v === selected ? "selected" : ""}>${esc(v)}</option>`).join("");
const navs = [
  ["today", "오늘", "house"],
  ["pantry", "냉장고", "refrigerator"],
  ["recipes", "레시피", "cooking-pot"],
  ["workout", "운동", "dumbbell"],
  ["journal", "기록", "notebook-pen"],
];
const names = {
  today: "오늘의 한끼",
  pantry: "나의 냉장고",
  recipes: "레시피 찾기",
  workout: "나의 운동",
  journal: "생활 기록",
};
let st = null,
  catalog = null,
  last = null,
  busy = false,
  timer = 0,
  inFlight = null,
  plans = [];
const dialog = $("#sheet");
function route() {
  const k = location.hash.slice(1);
  return navs.some((n) => n[0] === k) ? k : "today";
}
function go(k) {
  if (location.hash !== "#" + k) location.hash = k;
  else render();
}
function note(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("on");
  clearTimeout(timer);
  timer = setTimeout(() => t.classList.remove("on"), 3000);
}
function sheet(title, body) {
  $("#sheet-title").textContent = title;
  $("#sheet-body").innerHTML = body;
  dialog.scrollTop = 0;
  if (!dialog.open) dialog.showModal();
}
function close() {
  if (dialog.open) dialog.close();
}
function fields(data) {
  return Object.fromEntries(new FormData(data).entries());
}
async function api(path, method = "GET", data) {
  let res;
  try {
    res = await fetch(path, {
      method,
      cache: "no-store",
      headers: data ? { "Content-Type": "application/json" } : {},
      body: data ? JSON.stringify(data) : undefined,
    });
  } catch {
    throw Error("서버 연결을 확인한 뒤 다시 시도하세요.");
  }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    throw Error(typeof j.detail === "string" ? j.detail : "요청을 처리하지 못했습니다.");
  }
  return res.status === 204 ? null : res.json();
}
function markWaiting(text) {
  const b = dialog.open ? $("#sheet-body") : $("#main");
  let el = b.querySelector("[data-progress]");
  if (!el) {
    el = document.createElement("p");
    el.dataset.progress = "";
    el.className = "hint";
    el.setAttribute("role", "status");
    b.prepend(el);
  }
  el.textContent = text;
}
async function send(message, params = {}, show = false) {
  if (busy) return;
  busy = true;
  markWaiting("요청을 처리하고 있어요…");
  document.body.setAttribute("aria-busy", "true");
  const key = JSON.stringify([message, params]);
  if (!inFlight || inFlight.key !== key)
    inFlight = { key, id: globalThis.crypto?.randomUUID?.() || String(Date.now()) + Math.random() };
  try {
    const r = await api("/api/chat", "POST", { message, params, request_id: inFlight.id });
    inFlight = null;
    last = r;
    st = { ...r, 계획: r["현재 추천"] };
    render();
    if (show) showResult(message, r);
    else {
      close();
      note("반영했어요.");
    }
    return r;
  } catch (e) {
    if (!/연결/.test(e.message)) inFlight = null;
    markWaiting(e.message);
    note(e.message);
  } finally {
    busy = false;
    document.body.removeAttribute("aria-busy");
  }
}
function section(title, action, label) {
  return `<div class="section-head"><h2>${esc(title)}</h2>${action ? btn(label, action, "linkbtn", "chevron-right") : ""}</div>`;
}
function disk(icon, color = "") {
  return `<span class="disk ${color}">${ic(icon)}</span>`;
}
function hand(icon, label, action, value, color = "") {
  return `<button class="tile" data-do="${action}">${disk(icon, color)}<strong>${label}</strong><small>${esc(value)}</small></button>`;
}
function heading(k, sub) {
  return `<div class="heading"><div><div class="eyeline">${{ today: "나의 대시보드", pantry: "식재료 관리", recipes: "식단 탐색", workout: "움직임", journal: "데일리 로그" }[k]}</div><h1>${names[k]}</h1>${sub ? `<p class="sub">${esc(sub)}</p>` : ""}</div></div>`;
}
function dateLabel(day) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    weekday: "short",
    timeZone: "Asia/Seoul",
  }).format(new Date(day + "T12:00:00+09:00"));
}
function coach() {
  return `<button data-do="chat" class="btn alt agent-input">${ic("sparkles")}<span>한끼 코치에게 물어보기</span>${ic("arrow-right")}</button>`;
}
function todayView() {
  const p = st["계획"],
    lots = st["포장"],
    title = p["메뉴"];
  const fresh = lots.length === 0;
  return (
    heading("today", "냉장고 속 재료로 식사와 운동을 계획해요.") +
    `<div class="dashboard"><div class="stack"><article class="hero"><img src="/static/table.webp" alt="두부 달걀찜을 담은 그릇과 초록색 식탁보"><div class="hero-copy"><span class="hero-kicker">${ic("leaf")} ${title === "두부 달걀찜" ? "내 재료로 만드는 한 끼" : "오늘의 레시피"}</span><h2>두부 달걀찜</h2><div class="meta"><span>${ic("clock-3")} 15분</span><span>·</span><span>${ic("utensils")} 1인분</span></div>${btn("레시피 보기", "featured", "btn light", "arrow-up-right")}</div></article>
 <section>${section("나의 냉장고", "pantry", "전체 보기")}<div class="card soft"><div class="row">${disk("refrigerator")}<div><h3>${fresh ? "첫 재료를 넣어보세요" : esc(st["냉장고"].slice(0, 3).join(" · ") || "기한이 지난 포장을 확인하세요")}</h3><p class="muted">${fresh ? "재료 이름만 입력해도 추천을 시작해요." : `사용 가능한 재료 ${st["냉장고"].length}종 · 등록 포장 ${lots.length}개`}</p></div></div><div class="actions">${btn("재료 추가", "lot", "btn", "plus")}${fresh ? "" : btn("추천 식단 확인", "meal", "btn alt", "utensils")}</div></div></section>
 <section>${section("지금 할 일")}<div class="tiles">${hand("utensils", "식단 선택", "recipes", title || "메뉴로 찾아보기")}${hand("dumbbell", "운동 시작", "workout", st["운동 계획"].body + " 루틴", "peach")}${hand("droplet", "물 기록", "water", "섭취량 더하기", "blue")}</div></section>${coach()}</div>
 <aside class="stack"><section class="card intake">${section("오늘의 기록", "journal", "자세히")}${metricRows()}</section>
 <section class="card ink"><div class="hero-kicker">${ic("dumbbell")} 오늘의 움직임</div><p class="plan-name">${esc(st["운동 계획"].move || "가벼운 휴식")}</p><p class="muted">${esc(st["운동 계획"].summary)}</p><div class="actions">${btn("루틴 보기", "workout", "btn light", "arrow-right")}</div></section>
 <section class="card">${section("나의 일정", "plans", "관리")}<p class="muted">식사와 운동 시간을 저장하고 겹치는 일정을 확인해요.</p></section></aside></div>`
  );
}
const metrics = [
  ["kcal", "섭취 열량", "kcal", "flame", "peach"],
  ["protein_g", "단백질", "g", "egg", ""],
  ["water_ml", "물", "mL", "droplet", "blue"],
  ["sleep_hours", "수면", "시간", "moon", ""],
];
function metricRows() {
  return metrics
    .map(([k, n, u, i, c]) => {
      const v = st["건강"].totals[k];
      return `<div class="row">${disk(i, c)}<div><strong>${n}</strong><small>${v.source || "기록 전"}</small></div><span class="value">${fmt(v.value)} <small>${u}</small></span></div>`;
    })
    .join("");
}
function expiry(d) {
  if (!d) return ["기한 미입력", false];
  const delta = Math.round((Date.parse(d) - Date.parse(st["날짜"])) / 86400000);
  return [
    delta < 0 ? "기한 지남" : delta === 0 ? "오늘까지" : delta <= 3 ? `${delta}일 남음` : d,
    delta <= 3,
  ];
}
function pantryView() {
  let items = [...st["포장"]].sort((a, b) => (a.expires || "9999").localeCompare(b.expires || "9999"));
  return (
    heading("pantry", "포장에 적힌 소비기한 순서로 먼저 쓸 재료를 확인해요.") +
    `<div class="panelgrid wideleft"><section class="card"><div class="section-head"><h2>보관 중인 재료 <small>${items.length}</small></h2>${btn("재료 추가", "lot", "btn", "plus")}</div>
 ${items.length ? items.map((l) => `<div class="list-line"><div><strong>${esc(l.item)}</strong><small>${l.grams == null ? "용량 미입력" : fmt(l.grams) + " g"} · ${esc(l.expires || "날짜 미입력")}</small></div>${pill(...expiry(l.expires))}${btn("삭제", "remove", "linkbtn", "", l.id)}</div>`).join("") : '<p class="empty">냉장고가 비어 있어요. 달걀이나 두부처럼 지금 있는 재료 하나부터 등록해 보세요.</p>'}
 </section><div class="stack"><section class="card soft">${section("재료로 만들 수 있는 메뉴")}<p class="plan-name">${esc(st["계획"]["메뉴"] || st["계획"]["안내"] || "남은 음식부터")}</p><div class="actions">${btn("식단 확인", "meal", "btn", "utensils")}</div></section><section class="card">${section("장바구니")}${cartRows()}</section><section class="card">${section("조리해 둔 음식")}${leftoverRows()}</section></div></div>`
  );
}
function cartRows() {
  const rows = Object.entries(st["장바구니"] || {});
  return rows.length
    ? rows
        .map(
          ([name, v]) =>
            `<div class="list-line"><div><strong>${esc(name)} · ${fmt(v.grams)}g</strong><small>${esc(v.meal)}</small><div class="btnbar">${btn("상품 조회", "shopping", "chip", "", name)}${btn("구입 후 입고", "bought", "chip", "", name)}${btn("목록에서 빼기", "uncart", "linkbtn", "", name)}</div></div></div>`,
        )
        .join("")
    : '<p class="muted">추천 식단에서 부족한 재료를 담아 보세요.</p>';
}
function leftoverRows() {
  const list = Object.entries(st["남은 음식"]);
  return list.length
    ? list
        .map(
          ([n, v]) =>
            `<div class="list-line"><div><strong>${esc(n)}</strong><small>${v}인분 남음</small></div>${btn("1인분 섭취", "eat", "chip", "check", n)}</div>`,
        )
        .join("")
    : '<p class="muted">조리를 기록하면 남은 분량이 여기에 표시돼요.</p>';
}
function recipesView() {
  const p = st["계획"];
  return (
    heading("recipes", "원하는 메뉴를 고르면 필요한 분량과 장보기 목록을 확인할 수 있어요.") +
    `<div class="panelgrid wideleft"><div class="stack"><section class="card soft">${section("내 조건에 맞는 식사")}<p class="plan-name">${esc(p["메뉴"] || p["안내"] || "남은 음식 우선")}</p><p class="muted">${esc(p["판단 기준"] || "")}</p><div class="actions">${btn("추천 상세", "meal", "btn", "utensils")}${btn("7일 식단", "week", "btn alt", "calendar-days")}</div></section>
 <section class="card">${section("레시피 목록")}<label class="sr" for="meal-filter">메뉴 검색</label><input id="meal-filter" class="chat-input" placeholder="메뉴나 재료로 검색"><div id="meal-list">${recipeList("")}</div></section></div><div class="stack"><section class="card">${section("레시피와 장보기")}${sourceForm("레시피", "메뉴 이름", "국내 레시피 조회")}<hr class="divider">${sourceForm("영상", "요리 이름", "YouTube · Instagram 찾기")}<hr class="divider">${sourceForm("쇼핑", "구입할 재료", "상품 조회")}</section>${coach()}</div></div>`
  );
}
function recipeList(term) {
  const rows = catalog.meals.filter(
    (m) => m.title.includes(term) || Object.keys(m.grams).some((x) => x.includes(term)),
  );
  return (
    rows
      .map(
        (m) =>
          `<div class="list-line"><div><strong>${esc(m.title)}</strong><small>${fmt(m.minutes)}분 · ${esc(Object.keys(m.grams).join(", "))}</small></div>${btn("선택", "choose", "chip", "", m.title)}</div>`,
      )
      .join("") || '<p class="empty">등록된 메뉴가 없습니다. 국내 레시피 조회에서 찾아보세요.</p>'
  );
}
function sourceForm(cmd, label, submit) {
  return `<form class="form" data-form="source" data-cmd="${cmd}"><label>${esc(label)}<input name="term" required maxlength="80"></label><button class="btn alt">${ic("search")}${esc(submit)}</button></form>`;
}
function workoutView() {
  const r = st["운동 계획"],
    logs = st["운동 기록"];
  return (
    heading("workout", "가용 시간과 운동 경험에 맞춰 오늘의 루틴을 조정해요.") +
    `<div class="panelgrid wideleft"><section class="card"><div class="card-head">${pill((r.level || "기본") + " · " + r.body)}${btn("조건 변경", "settings", "linkbtn", "sliders-horizontal")}</div><h2>${esc(r.move || r.summary)}</h2><p class="muted">${esc(r.reason || "")} · 휴식 포함 ${r.minutes}분</p><ol class="step-list">${r.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol><div class="actions">${btn("운동 완료 기록", "finish", "btn", "check")}${btn("일정에 담기", "plans", "btn alt", "calendar-days")}</div></section>
 <div class="stack"><section class="card">${section("근처 헬스장")}${sourceForm("헬스장", "동네나 역 이름", "카카오맵으로 찾기")}</section><section class="card">${section("최근 운동")}${
   logs.length
     ? logs
         .slice(-4)
         .reverse()
         .map(
           (x) =>
             `<div class="list-line"><strong>${esc(x.body)} · ${x.minutes}분</strong><small>${esc(x.effort)} · ${x.day}</small></div>`,
         )
         .join("")
     : '<p class="muted">완료 후 남긴 체감 난이도를 다음 루틴에 반영해요.</p>'
 }</section><section class="card"><details><summary>운동 자료와 출처</summary>${catalog.exercises.map((x) => `<div class="list-line"><div>${a(x.title, x.url)}<small>${esc(x.authors.join(", "))} · ${a("이용 조건", x.license)}</small></div></div>`).join("")}</details></section></div></div>`
  );
}
function journalView() {
  const j = st["건강"],
    w = j.week,
    max = Math.max(...w.map((x) => x.totals.water_ml.value || 0), 1);
  return (
    heading("journal", "직접 기록한 값과 연결한 건강 데이터의 출처를 함께 확인해요.") +
    `<div class="panelgrid"><div class="stack"><section class="card intake">${section("오늘의 섭취와 수면")}${metricRows()}<div class="btnbar">${btn("물 더하기", "water", "btn", "droplet")}${btn("수면 기록", "sleep", "btn alt", "moon")}</div></section><section class="card">${section("이번 주 수분 기록")}<div class="week">${w.map((x) => `<div><small>${fmt(x.totals.water_ml.value)}</small><i style="height:${Math.max(2, (45 * (x.totals.water_ml.value || 0)) / max)}px"></i><small>${x.day.slice(5)}</small></div>`).join("")}</div><p class="hint">단위 mL · 대시는 기록 전</p></section></div>
 <div class="stack"><section class="card soft">${section("나의 영양 목표", "settings", "설정")}${j.hints.length ? j.hints.map((h) => `<p><strong>${esc(h.label)}</strong> · 목표까지 ${fmt(h.remaining)}${h.label === "수분" ? "mL" : "g"}</p><p class="muted">${esc(h.advice)}</p>`).join("") : '<p class="muted">목표와 섭취량을 기록하면 남은 양을 계산해요.</p>'}</section><section class="card">${section("조리시간 분석")}<div class="facts"><div class="fact"><small>조리 횟수</small><b>${j.metrics.cooks}<span>회</span></b></div><div class="fact"><small>평균 오차</small><b>${fmt(j.metrics.planned_vs_actual_mae_min)}<span>분</span></b></div></div><p class="hint">메뉴별 최근 조리 기록 5건을 다음 예상 시간에 반영해요.</p></section><section class="card">${section("데이터 관리")}<div class="btnbar">${btn("건강 데이터 연결", "health", "btn alt", "heart-pulse")}${btn("계획과 일정", "plans", "btn alt", "calendar-days")}${btn("실행 이력", "logs", "btn alt", "notebook-text")}</div><p class="footnote">일상 생활을 위한 참고 정보입니다. 개인의 치료나 섭취 처방은 의료진과 상의하세요.</p><details><summary>내 데이터</summary><div class="btnbar"><a href="/api/export" download="hankki.json" class="chip">내 데이터 내려받기</a>${btn("기록 삭제", "erase", "chip danger")}<a href="/privacy" class="chip">개인정보 안내</a></div></details></section></div></div>`
  );
}
function render() {
  if (!st) return;
  const k = route();
  document.title = names[k] + " · 한끼";
  $("#date").textContent = dateLabel(st["날짜"]);
  $("#crumb").textContent = k === "today" ? "나의 대시보드" : "나의 생활 / " + names[k];
  const nav = navs
    .map(
      ([id, n, i]) =>
        `<a class="navitem" href="#${id}" ${id === k ? 'aria-current="page"' : ""}>${ic(i)}<span>${n}</span></a>`,
    )
    .join("");
  $("#side-nav").innerHTML = nav;
  $("#mobile-nav").innerHTML = nav;
  $("#main").innerHTML = {
    today: todayView,
    pantry: pantryView,
    recipes: recipesView,
    workout: workoutView,
    journal: journalView,
  }[k]();
}
