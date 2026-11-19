"use strict";
// 한끼 코치(Agent) 대화 화면: 상황을 말하면 추천·메뉴 확정·장보기·영상·조리 모드·운동·알림까지 이어서 진행한다.
// 대화 기록은 이 기기에만 저장한다(localStorage, 최근 40개). 실행 과정 전체는 서버의 실행 로그에 남는다.
const THREAD_KEY = "hk-thread-v1";
const STEPS = ["상황을 읽고 있어요", "냉장고와 소비기한을 비교하고 있어요", "후보 메뉴를 고르고 있어요", "할 일을 정리하고 있어요"];
let thread = loadThread(),
  waiting = null,
  waitTimer = 0,
  mediaCache = {},
  videoPick = {},
  results = {};

function loadThread() {
  try {
    const t = JSON.parse(localStorage.getItem(THREAD_KEY) || "[]");
    return Array.isArray(t) ? t : [];
  } catch {
    return [];
  }
}
function saveThread() {
  thread = thread.slice(-40);
  try {
    localStorage.setItem(THREAD_KEY, JSON.stringify(thread));
  } catch {}
}
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const hhmmOf = (t) => new Date(t).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });

function compact(msg, r) {
  // 서버 응답을 대화 카드에 필요한 값만 남겨 저장한다
  const p = r["계획"] || {},
    base = { role: "agent", id: uid(), at: Date.now(), answer: p["답변"] || "" };
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
  if (p["검색어"] && p["직접 검색"]) return { ...base, kind: "shopping", term: p["검색어"], links: p["직접 검색"], items: Object.values(p["자료"] || {}).flatMap((x) => (x.ok ? x.data.slice(0, 3) : [])), budget: p["예산 안내"] || "" };
  if ((r["추적"] || []).some((e) => e.name === "건강 안내")) return { ...base, kind: "health", note: p["안내"] || "" };
  if (p["주간"]) return { ...base, kind: "weekly", days: p["주간"] };
  const reminder = (r["추적"] || []).some((e) => e.name === "알림 해석");
  if (reminder) return { ...base, kind: "reminder", note: "알림을 만들었어요. 기록 탭에서 시간과 상태를 확인할 수 있어요." };
  const text = p["답변"] || p["안내"] || (p["메뉴"] ? `${p["메뉴"]} · ${p["판단 기준"] || ""}` : "") || "반영했어요.";
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

function welcome() {
  const lots = st?.["포장"] || [];
  const soon = [...lots].filter((l) => l.expires).sort((a, b) => a.expires.localeCompare(b.expires)).slice(0, 3);
  return `<div class="bubble agent welcome"><div class="avatar">${ic("sparkles")}</div><div class="bubble-body">
    <p class="lead">안녕하세요, 한끼 코치예요.</p>
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
    ["조금만 사면", "1~2가지만 사면 만들 수 있어요"],
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
    body += m.done.length ? `<p class="sec">제가 진행한 일</p>${doneList(m)}` : m.more ? `<p>이미 보여 드린 메뉴를 빼고 다른 후보를 골랐어요.</p>` : `<p>${esc(m.note || "조건에 맞는 메뉴가 없어요. 시간이나 조건을 바꿔 말해 주세요.")}</p>`;
    body += m.groups || m.picks.length ? `${m.groups ? "" : '<p class="sec">추천 후보</p>'}${picksList(m)}` : "";
    body += m.menu && !m.more
      ? `<div class="cta">${btn(`${m.servings}인분 조리 시작`, "agentCook", "btn", "timer", JSON.stringify([m.menu, m.servings]))}${m.cart ? btn("장바구니 보기", "pantry", "btn alt", "shopping-bag") : ""}</div><p class="sec">${esc(m.menu)} 영상</p><div class="media">${mediaBlock(m)}</div>`
      : "";
    body += m.how ? `<p class="footnote">판단 · ${esc(m.how)}${m.why ? " · " + esc(m.why) : ""}</p>` : "";
  } else if (m.kind === "workout") {
    const r = m.routine;
    const ex = r.exercises || [];
    body += `<div class="workout-card"><div class="wk-head"><div class="wk-mini">${ex[0] && typeof figureSVG === "function" ? figureSVG(motionOf(ex[0].name), null, { label: ex[0].name }) : disk("dumbbell", "peach")}</div><div><strong>${esc(r.move || r.summary)}</strong><small>${esc(r.level || "")} · ${esc(r.body)} · 휴식 포함 ${r.minutes}분</small></div></div>${r.steps.length ? `<ol class="step-list">${r.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : `<p>${esc(r.summary)}</p>`}</div>
      <div class="cta">${r.steps.length ? btn("운동 모드 시작", "wkStart", "btn", "timer") : ""}${btn("운동 탭에서 보기", "workout", "btn alt", "dumbbell")}</div>
      ${(m.options || []).length ? `<p class="sec">다른 선택지</p><div class="picks">${m.options.map((o) => `<article class="pick"><div><strong>${esc(o.title)}</strong><small>${esc(o.why)} · ${esc(o.summary || "")}</small></div>${btn("이걸로", "wkApply", "chip", "", JSON.stringify(o.apply))}</article>`).join("")}</div>` : ""}`;
  } else if (m.kind === "shopping") {
    body += `<p><strong>${esc(m.term)}</strong> 상품을 찾아봤어요.</p>${m.items.length ? `<div class="picks">${m.items.map((x) => `<article class="pick"><div><strong>${x.url ? a(x.title, x.url) : esc(x.title)}</strong><small>${x.price_krw != null ? fmt(x.price_krw) + "원 · " : ""}${esc(x.merchant || "")}${x["100g당 가격"] ? " · 100g당 " + fmt(x["100g당 가격"]) + "원" : ""}</small></div></article>`).join("")}</div>` : '<p class="hint">쇼핑 API 키가 없어 상품 목록 대신 바로 검색할 수 있는 링크를 드려요.</p>'}<div class="cta">${Object.entries(m.links).map(([k, u]) => `<a class="btn alt" href="${esc(u)}" rel="noopener noreferrer">${esc(k)} ↗</a>`).join("")}</div>${m.budget ? `<p class="footnote">${esc(m.budget)}</p>` : ""}`;
  } else if (m.kind === "health") {
    body += `<p>${esc(m.note)}</p><div class="cta">${btn("건강 체크 입력", "healthForm", "btn", "heart-pulse")}${btn("기록 탭 열기", "journal", "btn alt")}</div>`;
  } else if (m.kind === "weekly") {
    body += `<p>현재 냉장고 기준 7일 식단 초안이에요.</p><div class="picks">${m.days.map((d) => `<article class="pick"><b>${esc(d.day.slice(8))}</b><div><strong>${esc(d.meal || "가능한 메뉴 없음")}</strong><small>${esc(d.workout)} · 추가할 재료 ${Object.keys(d.missing).length}종</small></div>${d.meal ? btn("조리", "agentCook", "chip", "timer", JSON.stringify([d.meal, 1])) : ""}</article>`).join("")}</div>`;
  } else if (m.kind === "reminder") {
    body += `<p>${esc(m.note)}</p><div class="cta">${btn("알림 보기", "journal", "btn alt", "notebook-pen")}</div>`;
  } else if (m.kind === "error") {
    body += `<p>${esc(m.note)}</p><div class="cta">${btn("다시 보내기", "agentRetry", "btn alt", "send", m.retry)}</div>`;
  } else {
    body += m.answer ? "" : `<p>${esc(m.note)}</p>`;
    body += m.detail && results[m.id] ? `<div class="cta">${btn("결과 자세히 보기", "agentDetail", "btn alt", "arrow-up-right", m.id)}</div>` : "";
  }
  return `<div class="bubble agent" id="m-${m.id}"><div class="avatar">${ic("sparkles")}</div><div class="bubble-body">${body}<time>${hhmmOf(m.at)}</time></div></div>`;
}

function typing() {
  if (!waiting) return "";
  return `<div class="bubble agent typing" role="status"><div class="avatar">${ic("sparkles")}</div><div class="bubble-body"><div class="dots"><i></i><i></i><i></i></div><ol class="progress-steps">${STEPS.map((s, i) => `<li class="${i < waiting.step ? "done" : i === waiting.step ? "on" : ""}">${esc(s)}</li>`).join("")}</ol></div></div>`;
}

function agentView() {
  const msgs = thread
    .map((m) => (m.role === "user" ? `<div class="bubble user"><div class="bubble-body"><p>${esc(m.text)}</p><time>${hhmmOf(m.at)}</time></div></div>` : agentCard(m)))
    .join("");
  return `<div class="chat">
    <div class="chat-head"><div><div class="eyeline">AI 코치</div><h1>한끼 코치</h1></div>${thread.length ? btn("대화 지우기", "agentClear", "linkbtn", "trash-2") : ""}</div>
    <div class="chat-log" id="chat-log" aria-live="polite">${welcome()}${msgs}${typing()}</div>
    <form class="composer" data-form="agentAsk"><div class="chips">${chipsFor().map((x) => btn(x, "agentSay", "chip", "", x)).join("")}</div>
      <div class="composer-row"><label class="sr" for="agent-input">지금 상황</label><textarea id="agent-input" name="message" rows="1" maxlength="1000" required placeholder="지금 상황을 말해 주세요"></textarea><button class="send" type="submit" aria-label="보내기" ${waiting ? "disabled" : ""}>${ic("send")}</button></div>
      <p class="footnote">일반 생활 참고 정보예요. 질환·치료는 의료진과 상의하세요.</p></form></div>`;
}

function scrollChat() {
  const log = $("#chat-log");
  if (log) log.scrollTop = log.scrollHeight;
  if (route() === "agent") window.scrollTo(0, document.body.scrollHeight);
}

async function agentAsk(text) {
  text = String(text || "").trim();
  if (!text || waiting) return;
  thread.push({ role: "user", text, at: Date.now() });
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
    const r = await api("/api/chat", "POST", { message: text, request_id: uid() });
    last = r;
    st = { ...r, 계획: r["현재 추천"] };
    const m = compact(text, r);
    results[m.id] = r;
    thread.push(m);
    if (m.kind === "auto" && m.menu) loadMedia(m.menu);
  } catch (err) {
    thread.push({ role: "agent", id: uid(), at: Date.now(), kind: "error", note: err.message, retry: text });
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

const MOTION_HINT = { 걷기: "walk", 스텝: "walk", 스쿼트: "squat", 의자: "squat", 런지: "lunge", "벽 밀기": "wallpush", "벽 푸시업": "wallpush", 인클라인: "incline", 푸시업: "pushup", 플랭크: "plank", 숄더: "shouldertap", 버드독: "birddog", 데드버그: "deadbug", "엎드린": "prone", 스노우엔젤: "prone", 프론: "prone", "벽 슬라이드": "wallslide", 버티기: "raise", 레이즈: "raise", 컬: "curl", 로우: "row" };
function motionOf(name) {
  return Object.entries(MOTION_HINT).find(([k]) => name.includes(k))?.[1] || "walk";
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
  agentRetry: (text) => agentAsk(text),
  agentClear: () => {
    if (!confirm("이 기기의 코치 대화 기록을 지울까요? (실행 로그는 서버에 남아요)")) return;
    thread = [];
    saveThread();
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
    if (!confirm("지금 냉장고와 장바구니를 비우고 예시 재료 18가지로 채울까요?")) return;
    const r = await api("/api/demo", "POST", {});
    st = { ...r, 계획: r["현재 추천"] };
    render();
    note("예시 재료로 채웠어요.");
  },
});
Object.assign(forms, {
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
