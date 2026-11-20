"use strict";
// 한끼 코치(Agent) 대화 화면: 상황을 말하면 추천·메뉴 확정·장보기·영상·조리 모드·운동·알림까지 이어서 진행한다.
// 대화 기록은 이 기기에만 저장한다(localStorage, 날짜별 최근 40개). 실행 과정 전체는 서버의 실행 로그에 남는다.
const THREAD_KEY = "hk-thread-v1";
const STEPS = ["상황을 읽고 있어요", "냉장고와 소비기한을 비교하고 있어요", "후보 메뉴를 고르고 있어요", "할 일을 정리하고 있어요"];
const koreaDate = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" });
const chatDay = (at = Date.now()) => koreaDate.format(at);
let archiveDay = "";
let thread = loadThread(),
  waiting = null,
  waitTimer = 0,
  mediaCache = {},
  videoPick = {},
  results = {};

function loadThread() {
  try {
    const t = JSON.parse(localStorage.getItem(THREAD_KEY) || "[]");
    return Array.isArray(t) ? t.filter((entry) => entry && Number.isFinite(entry.at)) : [];
  } catch {
    return [];
  }
}
function saveThread() {
  const counts = new Map();
  thread = thread.slice().reverse().filter((entry) => {
    const day = chatDay(entry.at);
    counts.set(day, (counts.get(day) || 0) + 1);
    return counts.get(day) <= 40;
  }).reverse();
  try {
    localStorage.setItem(THREAD_KEY, JSON.stringify(thread));
  } catch { note("이 기기의 대화 저장 공간이 부족해요."); }
}
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const hhmmOf = (t) => new Date(t).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit" });

function compact(msg, r) {
  // 서버 응답을 대화 카드에 필요한 값만 남겨 저장한다
  const p = r["계획"] || {},
    command = (r["추적"] || []).find((e) => e.name === "요청 분류")?.payload?.decision,
    base = { role: "agent", id: uid(), at: Date.now(), command, answer: p["답변"] || "" };
  if (p["자동 진행"])
    return {
      ...base,
      kind: "auto",
      done: p["자동 진행"].map((d) => ({ ...d, undone: false })),
      picks: p["추천 후보"] || [],
      groups: p["선택지"] || null,
      more: !!p["더보기"],
      menu: p["확정 메뉴"] || (p["더보기"] ? "" : p["추천 후보"]?.[0]?.["메뉴"] || ""),
      servings: p["인분"] || 1,
      how: p["판단 방법"] || "",
      why: p["판단 이유"] || "",
      cook: !!p["조리 모드"],
      note: p["안내"] || "",
      cart: Object.keys(r["장바구니"] || {}).length,
    };
  if (p["운동 루틴"]) return { ...base, kind: "workout", routine: p["운동 루틴"], options: p["운동 선택지"] || [], note: p["안내"] || "" };
  if (p["검색어"] && p["직접 검색"]) {
    const providers = { 쇼핑: ["naver", "coupang"], 영상: ["youtube", "instagram"], 헬스장: ["gyms"] };
    const items = (providers[command] || []).flatMap((key) => {
      const result = p["자료"]?.[key];
      return result?.ok && Array.isArray(result.data) ? result.data.slice(0, 3) : [];
    });
    return { ...base, kind: "search", term: p["검색어"], links: p["직접 검색"], items, budget: p["예산 안내"] || "" };
  }
  if (p["근거 문서"]) return { ...base, kind: "knowledge", answer: p["답변"] || "", evidence: p["근거 문서"], note: p["안내"] || "", source: p["출처"] || "" };
  if ((r["추적"] || []).some((e) => e.name === "건강 안내")) return { ...base, kind: "health", note: p["안내"] || "" };
  if (p["주간"]) return { ...base, kind: "weekly", days: p["주간"] };
  const reminder = (r["추적"] || []).some((e) => e.name === "알림 해석");
  if (reminder) return { ...base, kind: "reminder", note: "알림을 만들었어요. 기록 탭에서 시간과 상태를 확인할 수 있어요." };
  const lookup = p["조회"];
  const lookupNote = lookup?.ok === false ? (errors[lookup.error] || "조회 결과를 가져오지 못했어요.") : lookup?.ok ? "조회 결과를 확인하세요." : "";
  const text = p["답변"] || p["안내"] || lookupNote || (p["메뉴"] ? `${p["메뉴"]} · ${p["판단 기준"] || ""}` : "") || "반영했어요.";
  return { ...base, kind: "text", note: text, detail: !!(p["자료"] || p["조회"] || p["요청 메뉴"] || p["주간"]), msg };
}

function chipsFor() {
  const lots = st?.["포장"] || [];
  const soon = [...lots].filter((l) => l.expires).sort((a, b) => a.expires.localeCompare(b.expires))[0];
  return [
    soon ? `${soon.item}부터 써서 저녁 만들어줘` : "냉장고에 있는 걸로 저녁 추천해줘",
    "퇴근했는데 20분밖에 없어. 단백질 위주로",
    "둘이 먹을 거고 있는 재료로만 해줘",
    "어깨 운동 30분 하고 싶어",
    "물 2시간마다 알려줘",
  ];
}

// 카탈로그의 코치 사진을 표시하고 사진이 설정되지 않은 역할에는 기본 아이콘을 쓴다.
const PERSONAS = {
  chef: {
    name: "한끼 셰프",
    title: "요리 전문 코치",
    svg: `<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="32" fill="#eef0ee"/><rect x="27.5" y="38" width="9" height="8" fill="#e6bf9f"/><path d="M5 64c1-12 9-19 27-19s26 7 27 19z" fill="#3a3b3f"/><path d="M23.5 44.5c2 3.5 5 5 8.5 5s6.5-1.5 8.5-5v-2.5h-17z" fill="#2c2d31"/><path d="M29.2 44.6l2.8 5.4 2.8-5.4z" fill="#e6bf9f"/><path d="M32 50v14" stroke="#29292c" stroke-width=".8"/><path d="M10 64c2-5 9-9 22-9s20 4 22 9z" fill="#4a4b50"/><path d="M14 60c5-3 11-4 18-4" stroke="#3a3b3f" stroke-width="1.2" fill="none"/><ellipse cx="44" cy="58" rx="3.6" ry="2.3" fill="#ecc3a3"/><ellipse cx="21.6" cy="30" rx="1.7" ry="2.7" fill="#e6bf9f"/><ellipse cx="42.4" cy="30" rx="1.7" ry="2.7" fill="#e6bf9f"/><ellipse cx="32" cy="29" rx="10" ry="12" fill="#f0cfb2"/><path d="M21.8 28c-1.6-9.6 4.4-15 11.2-15 7.8 0 12.2 5.2 10.4 14-.8-3.4-2-5.4-3.6-6.6-3.6 1.6-9.2 1.4-13.4-.6-2.4 1.6-3.8 4.2-4.6 8.2z" fill="#16181b"/><path d="M30.5 13.4c-2.6 1.8-4.2 4.2-4.5 7" stroke="#2b2e33" stroke-width="1" fill="none"/><path d="M25.8 26.2q2.2-1.2 4.4-.4M33.8 25.8q2.2-.8 4.4.4" stroke="#16181b" stroke-width="1.3" fill="none" stroke-linecap="round"/><ellipse cx="28" cy="29.8" rx="1.35" ry="1" fill="#1d1d1f"/><ellipse cx="36" cy="29.8" rx="1.35" ry="1" fill="#1d1d1f"/><path d="M26.4 29.2q1.6-.8 3.2 0M34.4 29.2q1.6-.8 3.2 0" stroke="#c99b7c" stroke-width=".7" fill="none"/><path d="M32 31v3.2" stroke="#d9ab8c" stroke-width="1" stroke-linecap="round"/><path d="M29.4 36.4q2.6 1.1 5.2 0" stroke="#a9654f" stroke-width="1.3" fill="none" stroke-linecap="round"/></svg>`,
  },
  trainer: {
    name: "한끼 트레이너",
    title: "퍼스널 트레이너",
    svg: `<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="32" fill="#3b3d40"/><rect x="25.5" y="37" width="13" height="9" fill="#cf9570"/><path d="M1 64c1-12 7-19 16-21.5l15 3.5 15-3.5c9 2.5 15 9.5 16 21.5z" fill="#f7f7f5"/><path d="M27.5 44.5l4.5 9 4.5-9z" fill="#cf9570"/><path d="M23.5 43.5l8.5 8-3.6 3.4-7.4-8.6zM40.5 43.5l-8.5 8 3.6 3.4 7.4-8.6z" fill="#fff" stroke="#d8d8d4" stroke-width=".6"/><circle cx="32" cy="58" r=".9" fill="#cfcfca"/><circle cx="32" cy="62" r=".9" fill="#cfcfca"/><path d="M14 50c1 5 1 10 0 14M50 50c-1 5-1 10 0 14" stroke="#e2e2de" stroke-width="1" fill="none"/><ellipse cx="20.3" cy="29" rx="2" ry="3" fill="#cf9570"/><ellipse cx="43.7" cy="29" rx="2" ry="3" fill="#cf9570"/><ellipse cx="32" cy="28.5" rx="12" ry="12.6" fill="#dca582"/><path d="M20 26c-.4-8.4 4.8-14 12-14s12.6 5.4 12 14c-1-3.4-2.6-5.4-4.6-5.8-1.4 2-4.2 3-7.4 3s-6-1-7.6-3c-1.8.4-3.4 2.4-4.4 5.8z" fill="#1e1a17"/><path d="M21.5 31c1 7.6 5.2 10.6 10.5 10.6s9.5-3 10.5-10.6c-2 4.2-5.4 6.2-10.5 6.2s-8.5-2-10.5-6.2z" fill="#4a3a30" opacity=".5"/><path d="M25 25.2q2.8-1.4 5.4-.2M33.6 25q2.6-1.2 5.4.2" stroke="#1e1a17" stroke-width="1.9" fill="none" stroke-linecap="round"/><ellipse cx="28" cy="29.4" rx="1.4" ry=".95" fill="#1e1a17"/><ellipse cx="36" cy="29.4" rx="1.4" ry=".95" fill="#1e1a17"/><path d="M26.2 28.7q1.8-.9 3.6 0M34.2 28.7q1.8-.9 3.6 0" stroke="#a8735a" stroke-width="1" fill="none" stroke-linecap="round"/><path d="M32 30.5v3.6" stroke="#c38c69" stroke-width="1.1" stroke-linecap="round"/><path d="M28.4 35.6q3.6-1.6 7.2 0" stroke="#3a2c24" stroke-width="1.8" fill="none" stroke-linecap="round"/><path d="M29.6 37.8h4.8" stroke="#8a4f38" stroke-width="1.2" stroke-linecap="round"/></svg>`,
  },
  ai: {
    name: "한끼 AI",
    title: "생활 코치 비서",
    svg: `<svg viewBox="0 0 64 64" aria-hidden="true" class="ai-orb"><defs><radialGradient id="hk-ai-core"><stop offset="0" stop-color="#ffffff"/><stop offset=".45" stop-color="#9ff0ff"/><stop offset="1" stop-color="#1fb6ea"/></radialGradient><radialGradient id="hk-ai-glow"><stop offset="0" stop-color="#2ccbff" stop-opacity=".55"/><stop offset="1" stop-color="#2ccbff" stop-opacity="0"/></radialGradient></defs><circle cx="32" cy="32" r="32" fill="#0a1622"/><path d="M0 12h64M0 22h64M0 32h64M0 42h64M0 52h64M12 0v64M22 0v64M32 0v64M42 0v64M52 0v64" stroke="#12304a" stroke-width=".5"/><circle cx="32" cy="32" r="24" fill="url(#hk-ai-glow)"/><g class="ai-ring"><circle cx="32" cy="32" r="22" fill="none" stroke="#2ccbff" stroke-opacity=".6" stroke-width=".9" stroke-dasharray="10 3 2 3"/></g><circle cx="32" cy="32" r="15.5" fill="none" stroke="#56dcff" stroke-width="5" stroke-dasharray="6.1 2"/><g class="ai-ring rev"><circle cx="32" cy="32" r="10.5" fill="none" stroke="#bff6ff" stroke-width="1.2" stroke-dasharray="3 2.5"/></g><circle cx="32" cy="32" r="6.5" fill="url(#hk-ai-core)"/><path d="M32 4v5M32 55v5M4 32h5M55 32h5" stroke="#56dcff" stroke-width="1.4" stroke-linecap="round"/></svg>`,
  },
};
const CHEF_COMMANDS = new Set("추천 집밥 외식 메뉴 대체 레시피 레시피저장 식품영양 검색 영양 미국영양 요리코치 조리 섭취 섭취삭제 사진식사 쇼핑 영상 영상링크 레시피찜 찜해제 분량확인 주간계획 장바구니담기 장바구니삭제 구매완료 입고 포장삭제 추가 삭제".split(" "));
const TRAINER_COMMANDS = new Set("운동 운동완료 운동자료 헬스장 부위 내루틴저장 내루틴삭제".split(" "));

function searchCommand(m) {
  if (m.command) return m.command;
  // 이전 버전은 세 종류의 검색을 모두 shopping 카드로 저장했다.
  if (m.links?.["카카오맵 검색"]) return "헬스장";
  if (m.links?.["YouTube 검색"]) return "영상";
  return "쇼핑";
}

function personaOf(m) {
  if (m.kind === "workout") return "trainer";
  if (["auto", "weekly"].includes(m.kind)) return "chef";
  if (m.kind === "knowledge") {
    const topic = m.evidence?.[0]?.topic;
    if (topic === "운동") return "trainer";
    if (topic === "영양" || topic === "식품안전") return "chef";
  }
  const command = ["shopping", "search"].includes(m.kind) ? searchCommand(m) : m.command || m.msg?.split(" ")[0];
  if (TRAINER_COMMANDS.has(command)) return "trainer";
  if (CHEF_COMMANDS.has(command)) return "chef";
  return "ai";
}
const avatar = (key) => {
  const img = typeof catalog !== "undefined" && catalog?.personas?.[key];
  return `<div class="avatar persona ${key}" title="${PERSONAS[key].name}">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : PERSONAS[key].svg}</div>`;
};
const signature = (key) => `<p class="persona-name"><b>${PERSONAS[key].name}</b><span>${PERSONAS[key].title}</span></p>`;

function welcome() {
  const lots = st?.["포장"] || [];
  const soon = [...lots].filter((l) => l.expires).sort((a, b) => a.expires.localeCompare(b.expires)).slice(0, 3);
  return `<div class="bubble agent welcome">${avatar("ai")}<div class="bubble-body">${signature("ai")}
    <p class="lead">안녕하세요, 한끼 AI예요.</p>
    <div class="team"><span>요리는</span>${avatar("chef")}<b>한끼 셰프</b><span>, 운동은</span>${avatar("trainer")}<b>한끼 트레이너</b><span>가 이어서 맡아요.</span></div>
    <p>지금 상황을 말해 주시면 냉장고 재료로 메뉴를 고르고, 부족한 재료 담기·조리 안내·영상·운동·알림까지 이어서 진행할게요.</p>
    <div class="fridge-mini">${ic("refrigerator")}<span>재료 ${st?.["냉장고"]?.length || 0}종</span>${soon.map((l) => `<span class="pill ${expiry(l.expires)[1] ? "warn" : ""}">${esc(l.item)} ${esc(expiry(l.expires)[0])}</span>`).join("")}</div>
  </div></div>`;
}

function doneList(m) {
  return `<ol class="done-list">${m.done
    .map(
      (d, i) =>
        `<li class="${d.undone ? "undone" : ""}">${ic(d.undone ? "x" : "circle-check")}<div><strong>${esc(d["작업"])}</strong><small>${esc(d.undone ? "되돌렸어요" : d["결과"])}</small></div>${d["되돌리기"] && !d.undone ? btn("되돌리기", "agentUndo", "linkbtn", "", JSON.stringify([m.id, i])) : ""}</li>`,
    )
    .join("")}</ol>`;
}

function pickRow(m, x, i) {
  const chosen = x["메뉴"] === m.menu;
  const action = x["국내"]
    ? btn("조리 모드", "cookModeExt", "chip", "timer", x.id)
    : chosen
      ? pill("선택됨")
      : btn("이걸로", "agentChoose", "chip", "", JSON.stringify([m.id, x["메뉴"]]));
  return `<article class="pick ${chosen ? "on" : ""}">${x["사진"] ? `<img class="pick-photo" src="${esc(x["사진"])}" alt="" loading="lazy" onerror="this.remove()">` : `<b>${i + 1}</b>`}<div><strong>${esc(x["메뉴"])}</strong><small>${x["근거"].map(esc).join(" · ")}</small></div>${action}</article>`;
}
function groupsList(m) {
  const g = m.groups;
  const sections = [
    ["바로 가능", "지금 재료로 바로 만들 수 있어요"],
    ["분량 확인", "있는 재료의 양만 확인하면 돼요"],
    ["조금만 사면", "부족한 재료가 1~2가지예요"],
    ["추가 재료 필요", "필요한 재료를 확인하세요"],
    ["국내 레시피", "식품안전나라 레시피에서 찾았어요"],
  ].filter(([k]) => g[k]?.length);
  if (!sections.length) return "";
  return sections.map(([k, d]) => `<p class="sec">${esc(k)} <span class="muted">· ${esc(d)}</span></p><div class="picks">${g[k].map((x, i) => pickRow(m, x, i)).join("")}</div>`).join("") + `<div class="cta">${btn("다른 후보 더 보기", "agentSay", "btn alt", "list-filter", "다른 후보 알려줘")}</div>`;
}
function picksList(m) {
  if (m.groups) return groupsList(m);
  if (!m.picks.length) return "";
  return `<div class="picks">${m.picks
    .map(
      (x, i) =>
        `<article class="pick ${x["메뉴"] === m.menu ? "on" : ""}"><b>${i + 1}</b><div><strong>${esc(x["메뉴"])}</strong><small>${x["근거"].map(esc).join(" · ")}</small></div>${x["메뉴"] === m.menu ? pill("선택됨") : btn("이걸로", "agentChoose", "chip", "", JSON.stringify([m.id, x["메뉴"]]))}</article>`,
    )
    .join("")}</div>`;
}

function mediaBlock(m) {
  const info = mediaCache[m.menu];
  if (info === undefined) return btn(`${m.menu} 영상 보기`, "agentMedia", "btn alt", "circle-play", m.menu);
  if (info === null) return '<p class="hint" role="status">영상을 찾고 있어요…</p>';
  const yt = info.youtube,
    ig = info.instagram,
    at = videoPick[m.menu] || 0;
  let html = "";
  if (yt.ok && yt.data.length) {
    const v = yt.data[Math.min(at, yt.data.length - 1)];
    html += ytFrame(v) + (yt.data.length > 1 ? `<div class="btnbar">${yt.data.map((x, i) => btn((i === at ? "▶ " : "") + x.title.slice(0, 22), "agentVideo", "chip", "", JSON.stringify([m.menu, i]))).join("")}</div>` : "");
  } else html += `<p class="hint">YouTube · ${esc(errors[yt.error] || "영상을 찾지 못했어요.")}</p>`;
  if (ig.ok && ig.data.length) html += ig.data.slice(0, 2).map((x) => igEmbed(x)).join("");
  else html += `<p class="hint">Instagram · ${esc(errors[ig.error] || "게시물이 없어요.")} ${a("해시태그에서 보기", info["직접 검색"].Instagram)}</p>`;
  return html + linkForm(m.menu);
}

function agentCard(m) {
  let body = m.answer ? `<p class="answer">${esc(m.answer)}</p>` : "";
  if (m.kind === "auto") {
    body += m.done.length ? `<p class="sec">제가 진행한 일</p>${doneList(m)}` : m.note ? `<p>${esc(m.note)}</p>` : m.more ? `<p>이미 보여 드린 메뉴를 빼고 다른 후보를 골랐어요.</p>` : `<p>${esc("조건에 맞는 메뉴가 없어요. 시간이나 조건을 바꿔 말해 주세요.")}</p>`;
    body += m.groups || m.picks.length ? `${m.groups ? "" : '<p class="sec">추천 후보</p>'}${picksList(m)}` : "";
    body += m.menu && !m.more
      ? `<div class="cta">${btn(`${m.servings}인분 조리 시작`, "agentCook", "btn", "timer", JSON.stringify([m.menu, m.servings]))}${m.cart ? btn("장바구니 보기", "pantry", "btn alt", "shopping-bag") : ""}</div><p class="sec">${esc(m.menu)} 영상</p><div class="media">${mediaBlock(m)}</div>`
      : "";
    body += m.how ? `<p class="footnote">판단 · ${esc(m.how)}${m.why ? " · " + esc(m.why) : ""}</p>` : "";
  } else if (m.kind === "workout") {
    const r = m.routine;
    const ex = r.exercises || [];
    body += `<div class="workout-card"><div class="wk-head"><div class="wk-mini">${ex[0]?.motion ? figureSVG(ex[0].motion, ex[0].prop, { label: ex[0].name }) : disk("dumbbell", "peach")}</div><div><strong>${esc(r.move || r.summary)}</strong><small>${esc(r.level || "")} · ${esc(r.body)} · 휴식 포함 ${r.minutes}분</small></div></div>${r.steps.length ? `<ol class="step-list">${r.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : `<p>${esc(r.summary)}</p>`}</div>
      <div class="cta">${r.steps.length ? btn("운동 모드 시작", "wkStart", "btn", "timer") : ""}${btn("운동 탭에서 보기", "workout", "btn alt", "dumbbell")}</div>
      ${(m.options || []).length ? `<p class="sec">다른 선택지</p><div class="picks">${m.options.map((o) => `<article class="pick"><div><strong>${esc(o.title)}</strong><small>${esc(o.why)} · ${esc(o.summary || "")}</small></div>${btn("이걸로", "wkApply", "chip", "", JSON.stringify(o.apply))}</article>`).join("")}</div>` : ""}`;
  } else if (m.kind === "search" || m.kind === "shopping") {
    const command = searchCommand(m);
    const label = { 헬스장: "근처 헬스장", 영상: "레시피 영상", 쇼핑: "장보기 상품" }[command];
    const rows = m.items.map((x) => {
      const details = [x.address || x.channel || x.merchant, x.published, x.price_krw != null && fmt(x.price_krw) + "원", x["100g당 가격"] && "100g당 " + fmt(x["100g당 가격"]) + "원"].filter(Boolean);
      return `<article class="pick"><div><strong>${a(x.title, x.url)}</strong><small>${esc(details.join(" · "))}</small></div></article>`;
    });
    body += `<p><strong>${esc(m.term)}</strong> · ${esc(label)}</p>`;
    body += rows.length ? `<div class="picks">${rows.join("")}</div>` : '<p class="hint">조회된 항목이 없어요. 아래 링크에서 직접 검색할 수 있어요.</p>';
    body += `<div class="cta">${Object.entries(m.links).map(([k, u]) => a(k, u)).join("")}</div>`;
    if (m.budget) body += `<p class="footnote">${esc(m.budget)}</p>`;
  } else if (m.kind === "knowledge") {
    body += m.evidence.length
      ? `<p class="sec">근거 문서</p><div class="evidence">${m.evidence.map((d) => `<article><strong>${esc(d.title)}</strong><p>${esc(d.excerpt)}</p><small>${a(d.source, d.url)} · 거리 ${d.distance}</small></article>`).join("")}</div><p class="footnote">${esc(m.source)} · 일반 생활 참고 정보예요.</p>`
      : `<p>${esc(m.note)}</p>`;
  } else if (m.kind === "health") {
    body += `<p>${esc(m.note)}</p><div class="cta">${btn("건강 체크 입력", "healthForm", "btn", "heart-pulse")}${btn("기록 탭 열기", "journal", "btn alt")}</div>`;
  } else if (m.kind === "weekly") {
    body += `<p>현재 냉장고 기준 7일 식단 초안이에요.</p><div class="picks">${m.days.map((d) => `<article class="pick"><b>${esc(d.day.slice(8))}</b><div><strong>${esc(d.meal || "가능한 메뉴 없음")}</strong><small>${esc(d.workout)} · 추가할 재료 ${Object.keys(d.missing).length}종</small></div>${d.meal ? btn("조리", "agentCook", "chip", "timer", JSON.stringify([d.meal, 1])) : ""}</article>`).join("")}</div>`;
  } else if (m.kind === "reminder") {
    body += `<p>${esc(m.note)}</p><div class="cta">${btn("알림 보기", "journal", "btn alt", "notebook-pen")}</div>`;
  } else if (m.kind === "error") {
    body += `<p>${esc(m.note)}</p><div class="cta">${btn("다시 보내기", "agentRetry", "btn alt", "send", m.id)}</div>`;
  } else {
    body += m.answer ? "" : `<p>${esc(m.note)}</p>`;
    body += m.detail && results[m.id] ? `<div class="cta">${btn("결과 자세히 보기", "agentDetail", "btn alt", "arrow-up-right", m.id)}</div>` : "";
  }
  const who = personaOf(m);
  return `<div class="bubble agent ${who}" id="m-${m.id}">${avatar(who)}<div class="bubble-body">${signature(who)}${body}<time>${hhmmOf(m.at)}</time></div></div>`;
}

function typing() {
  if (!waiting) return "";
  return `<div class="bubble agent typing" role="status">${avatar("ai")}<div class="bubble-body"><div class="dots"><i></i><i></i><i></i></div><ol class="progress-steps">${STEPS.map((s, i) => `<li class="${i < waiting.step ? "done" : i === waiting.step ? "on" : ""}">${esc(s)}</li>`).join("")}</ol></div></div>`;
}

function agentView() {
  const today = chatDay();
  const day = archiveDay || today;
  const history = thread.filter((entry) => chatDay(entry.at) === day);
  const days = [...new Set([today, ...thread.map((entry) => chatDay(entry.at))])].sort().reverse();
  const msgs = history.map((m) => m.role === "user"
    ? `<div class="bubble user"><div class="bubble-body"><p>${esc(m.text)}</p><time>${hhmmOf(m.at)}</time> ${btn("문구 수정", "editChatText", "linkbtn", "", thread.indexOf(m).toString())}</div></div>`
    : agentCard(m)).join("");
  const archived = day !== today;
  return `<div class="chat">
    <div class="chat-head"><h1>한끼 코치</h1></div>
    <div class="chat-history-tools"><label>대화 날짜 <select id="chat-day" ${waiting ? "disabled" : ""}>${days.map((value) => `<option value="${value}" ${value === day ? "selected" : ""}>${value === today ? "오늘 · " : ""}${value}</option>`).join("")}</select></label>
    ${history.length ? btn("이 날짜 대화 지우기", "agentClearDay", "linkbtn", "trash-2") : ""}
    ${thread.length ? btn("전체 대화 초기화", "agentClear", "linkbtn", "trash-2") : ""}</div>
    <div class="chat-log" id="chat-log" aria-live="polite">${archived ? "" : welcome()}${msgs}${typing()}</div>
    ${archived ? btn("오늘 대화로 돌아가기", "chatToday", "btn alt") + "</div>" : `    <form class="composer" data-form="agentAsk"><div class="chips">${chipsFor().map((x) => btn(x, "agentSay", "chip", "", x)).join("")}</div>
      <div class="composer-row"><label class="sr" for="agent-input">지금 상황</label><textarea id="agent-input" name="message" rows="1" maxlength="1000" required placeholder="지금 상황을 말해 주세요"></textarea><button class="send" type="submit" aria-label="보내기" ${waiting ? "disabled" : ""}>${ic("send")}</button></div>
      <p class="footnote">일반 생활 참고 정보예요. 질환·치료는 의료진과 상의하세요.</p></form></div>`}`;
}

function scrollChat() {
  const log = $("#chat-log");
  if (log) log.scrollTop = log.scrollHeight;
  if (route() === "agent") window.scrollTo(0, document.body.scrollHeight);
}

async function agentAsk(text, failed = null) {
  text = String(text || "").trim();
  if (!text || waiting) return;
  archiveDay = "";
  const started = failed?.at || Date.now();
  const requestId = failed?.requestId || uid();
  if (!failed) thread.push({ role: "user", text, at: started });
  saveThread();
  waiting = { step: 0 };
  if (route() !== "agent") go("agent");
  else render();
  scrollChat();
  clearInterval(waitTimer);
  waitTimer = setInterval(() => {
    if (!waiting) return;
    waiting.step = Math.min(STEPS.length - 1, waiting.step + 1);
    const box = document.querySelector(".typing .progress-steps");
    if (box) box.outerHTML = `<ol class="progress-steps">${STEPS.map((s, i) => `<li class="${i < waiting.step ? "done" : i === waiting.step ? "on" : ""}">${esc(s)}</li>`).join("")}</ol>`;
  }, 1400);
  try {
    const r = await api("/api/chat", "POST", { message: text, request_id: requestId });
    last = r;
    st = failed ? await api("/api/state") : { ...r, 계획: r["현재 추천"] };
    if (failed) thread = thread.filter((entry) => entry !== failed);
    const m = compact(text, r);
    m.at = started;
    results[m.id] = r;
    thread.push(m);
    if (m.kind === "auto" && m.menu) loadMedia(m.menu);
  } catch (err) {
    if (failed) Object.assign(failed, { note: err.message, requestId });
    else thread.push({ role: "agent", id: uid(), at: started, kind: "error", note: err.message, retry: text, requestId });
  } finally {
    waiting = null;
    clearInterval(waitTimer);
    saveThread();
    render();
    scrollChat();
  }
}

async function loadMedia(menu) {
  if (mediaCache[menu]) return;
  mediaCache[menu] = null;
  const meal = catalog?.meals?.find((x) => x.title === menu);
  try {
    mediaCache[menu] = await api("/api/guide/media", "POST", { menu, steps: meal ? meal.steps : [] });
  } catch {
    delete mediaCache[menu];
  }
  if (route() === "agent") render();
}

function findMsg(id) {
  return thread.find((m) => m.id === id);
}

// 공용: YouTube iframe · Instagram 임베드 · 링크 추가 양식 (조리 모드에서도 사용)
function ytFrame(v, start = 0) {
  return `<div class="video-wrap"><iframe src="https://www.youtube.com/embed/${esc(v.id)}?start=${start || 0}&rel=0&playsinline=1" title="${esc(v.title)}" allow="encrypted-media; picture-in-picture; fullscreen" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen loading="lazy"></iframe></div>`;
}
function igEmbed(x) {
  setTimeout(loadInstagram, 50);
  return `<blockquote class="instagram-media" data-instgrm-permalink="${esc(x.url)}" data-instgrm-version="14"><a href="${esc(x.url)}" rel="noopener noreferrer">${esc(x.title)}</a></blockquote>`;
}
function linkForm(menu) {
  return `<details class="link-add"><summary>YouTube·Instagram 링크로 추가</summary><form class="form inline-link" data-form="mediaLink"><input type="hidden" name="menu" value="${esc(menu)}"><input name="url" type="url" required aria-label="영상 링크" placeholder="https://www.youtube.com/watch?v=… 또는 https://www.instagram.com/reel/…"><button class="btn alt" type="submit">${ic("plus")}화면에 추가</button><p class="footnote">키가 없어도 붙인 링크는 이 메뉴의 화면과 조리 모드에서 바로 재생돼요.</p></form></details>`;
}

function agentResult(msg, r) {
  archiveDay = "";
  // 다른 화면에서 자동 진행 결과가 오면 대화 기록에 넣고 코치 화면으로 이동
  thread.push({ role: "user", text: msg, at: Date.now() });
  const m = compact(msg, r);
  results[m.id] = r;
  thread.push(m);
  saveThread();
  close();
  if (m.kind === "auto" && m.menu) loadMedia(m.menu);
  go("agent");
  setTimeout(scrollChat, 50);
}

Object.assign(action, {
  agentSay: (text) => agentAsk(text),
  situation: (text) => agentAsk(text),
  agentRetry: (id) => {
    const failed = findMsg(id);
    if (failed?.kind === "error") return agentAsk(failed.retry, failed);
  },
  chatToday: () => { archiveDay = ""; render(); },
  editChatText: (index) => {
    const entry = thread[Number(index)];
    if (waiting || entry?.role !== "user") return;
    sheet("대화 문구 수정", form("editChatText",
      field("기록할 문구", "text", "text", entry.text, "required maxlength=1000") +
      `<input type="hidden" name="index" value="${Number(index)}"><input type="hidden" name="at" value="${entry.at}">` +
      '<p class="hint">이 문구만 수정해요. 코치에게 다시 보내거나 식사·운동 기록을 바꾸지 않아요.</p>'));

  },
  agentClearDay: () => {
    const day = archiveDay || chatDay();
    if (waiting || !confirm(day + "의 코치 대화를 지울까요? 식사·운동 기록과 실행 로그는 유지됩니다.")) return;
    for (const entry of thread.filter((m) => chatDay(m.at) === day)) delete results[entry.id];
    thread = thread.filter((m) => chatDay(m.at) !== day);
    archiveDay = "";
    saveThread();
    render();
  },
  agentClear: () => {
    if (waiting || !confirm("이 기기의 모든 날짜 코치 대화를 지울까요? 식사·운동 기록과 실행 로그는 유지됩니다.")) return;
    resetCoachHistory();
    render();
  },
  agentChoose: async (raw) => {
    // 명령어로 바로 반영해 모델을 다시 부르지 않는다(빠름)
    const [id, menu] = JSON.parse(raw),
      m = findMsg(id);
    const r = await api("/api/chat", "POST", { message: "메뉴 " + menu, request_id: uid() });
    st = { ...r, 계획: r["현재 추천"] };
    if (m) {
      m.menu = menu;
      m.done.push({ 작업: "메뉴 변경", 결과: menu, 되돌리기: "메뉴 자동", undone: false });
      m.cart = Object.keys(r["장바구니"] || {}).length;
      saveThread();
      loadMedia(menu);
    }
    render();
    note(menu + "(으)로 바꿨어요.");
  },
  agentUndo: async (raw) => {
    const [id, i] = JSON.parse(raw),
      m = findMsg(id),
      d = m?.done[i];
    if (!d) return;
    let r = null;
    for (const c of [].concat(d["되돌리기"])) r = await api("/api/chat", "POST", { message: c, request_id: uid() });
    if (r) st = { ...r, 계획: r["현재 추천"] };
    d.undone = true;
    saveThread();
    render();
    note("되돌렸어요.");
  },
  agentCook: async (raw) => {
    const [title, servings] = JSON.parse(raw);
    await openGuide({ title, servings });
  },
  agentMedia: (menu) => loadMedia(menu),
  agentVideo: (raw) => {
    const [menu, i] = JSON.parse(raw);
    videoPick[menu] = i;
    render();
  },
  agentDetail: (id) => results[id] && showResult(findMsg(id)?.msg || "결과", results[id]),
  demo: async () => {
    if (!confirm("지금 냉장고와 장바구니를 비우고 예시 재료로 채울까요?")) return;
    const r = await api("/api/demo", "POST", {});
    st = { ...r, 계획: r["현재 추천"] };
    render();
    note("예시 재료로 채웠어요.");
  },
});
Object.assign(forms, {
  editChatText: (v) => {
    const entry = thread[Number(v.index)];
    if (entry?.role !== "user" || entry.at !== Number(v.at)) return note("대화가 변경됐어요. 다시 선택해 주세요.");
    if (!v.text.trim()) return note("문구를 입력해 주세요.");
    entry.text = v.text.trim().slice(0, 1000);
    saveThread();
    close();
    render();
  },
  agentAsk: (v, f) => {
    f.reset();
    return agentAsk(v.message);
  },
  chat: (v) => agentAsk(v.message),
  mediaLink: async (v) => {
    await api("/api/chat", "POST", { message: "영상링크", params: { menu: v.menu, url: v.url.trim() } });
    note("링크를 추가했어요.");
    delete mediaCache[v.menu];
    if (guide && dialog.open && $("#sheet-body .cook")) {
      mediaInfo = null;
      await ensureMedia();
    } else await loadMedia(v.menu);
  },
});
document.addEventListener("keydown", (e) => {
  // Enter 보내기, Shift+Enter 줄바꿈
  if (e.target.id === "agent-input" && e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    e.target.form.requestSubmit();
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "agent-input") {
    e.target.style.height = "auto";
    e.target.style.height = Math.min(140, e.target.scrollHeight) + "px";
  }
});

function resetCoachHistory() {
  thread = [];
  results = {};
  archiveDay = "";
  localStorage.removeItem(THREAD_KEY);
}
document.addEventListener("change", (event) => {
  if (event.target.id === "chat-day") {
    archiveDay = event.target.value === chatDay() ? "" : event.target.value;
    render();
  }
});
window.addEventListener("storage", (e) => {
  if (e.key !== THREAD_KEY && e.key !== null) return;
  thread = loadThread();
  if (!thread.some((entry) => chatDay(entry.at) === archiveDay)) archiveDay = "";
  if (route() === "agent") render();
});

function scheduleChatMidnight() {
  const now = Date.now();
  const tomorrow = Date.parse(chatDay(now) + "T00:00:00+09:00") + 86400000;
  setTimeout(() => {
    if (route() === "agent") render();
    scheduleChatMidnight();
  }, tomorrow - now + 100);
}
scheduleChatMidnight();
