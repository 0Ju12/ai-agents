"use strict";
const labels = {
  naver: "네이버 쇼핑",
  coupang: "쿠팡",
  youtube: "YouTube",
  instagram: "Instagram",
  gyms: "카카오맵",
  search: "해외 레시피",
  detail: "레시피 상세",
  calendars: "일정",
};
const errors = {
  MISSING_KEY: "서버에 API 키를 설정하면 조회할 수 있어요.",
  AUTH_FAILED: "인증 권한을 확인해 주세요.",
  NO_RESULT: "검색 결과가 없습니다.",
  NO_INDEX: "2회차 근거 문서 색인을 연결해 주세요.",
  SOURCE_UNAVAILABLE: "자료 제공처 연결을 확인해 주세요.",
  INVALID_INPUT: "검색어 또는 입력 형식을 확인해 주세요.",
  RATE_LIMIT: "제공처의 호출 한도에 도달했습니다.",
  CALENDAR_NOT_CONNECTED: "Google 캘린더 연결이 필요해요.",
  TIME_BUDGET: "조회 시간 한도에 도달했어요.",
};
function typed(value) {
  if (value == null) return "미확인";
  if (Array.isArray(value)) return value.map(typed).join(" · ");
  if (typeof value === "object")
    return Object.entries(value)
      .map(([k, v]) => esc(k) + " " + typed(v))
      .join(" · ");
  return esc(value);
}
function provider(r) {
  if (!r?.ok)
    return `<p class="hint">${esc(errors[r?.error] || "자료를 확인하지 못했어요.")} ${r?.setting ? esc(r.setting) : ""}</p>`;
  const arr = Array.isArray(r.data) ? r.data : [r.data];
  return (
    `<p class="hint">${esc(r.source || "조회 결과")}</p>` +
    (arr.length
      ? arr
          .map((x) => {
            if (typeof x !== "object" || !x) return `<p>${typed(x)}</p>`;
            const title = x.title || x["메뉴"] || x["식품"] || x.product || x.id || "조회 결과";
            return `<article><strong>${x.url ? a(title, x.url) : esc(title)}</strong>${x.price_krw != null ? `<p>${fmt(x.price_krw)}원 · ${esc(x.merchant)}</p>` : ""}${Object.entries(
              x,
            )
              .filter(
                ([k]) =>
                  ![
                    "url",
                    "title",
                    "메뉴",
                    "식품",
                    "product",
                    "id",
                    "merchant",
                    "price_krw",
                    "license",
                  ].includes(k),
              )
              .map(
                ([k, v]) =>
                  `<div class="hint">${esc({ published: "게시일", views: "조회수", views_per_day: "일평균 조회수", address: "주소", likes: "좋아요", comments: "댓글", channel: "채널", excerpt: "근거 문서", start: "시작", end: "종료", distance: "검색 거리", ingredients: "재료", instructions: "조리법", basis: "기준량", kcal: "열량(kcal)", protein_g: "단백질(g)" }[k] || k)} · ${typed(v)}</div>`,
              )
              .join("")}</article>`;
          })
          .join("")
      : '<p class="hint">등록된 일정이 없어요.</p>')
  );
}
function trace(events) {
  let names = {
    node_start: "시작",
    node_end: "완료",
    tool_call: "호출",
    tool_result: "결과",
    replan: "재계획",
    evaluation: "검증",
    plan: "작업 목록",
    llm_decision: "판단",
    worker_result: "작업 결과",
    cache_hit: "결과 재사용",
    error: "안내",
    diagnosis: "진단",
  };
  return `<ol class="trace">${(events || []).map((x) => `<li class="${x.type === "replan" ? "again" : ""}"><b>${esc(names[x.type] || x.type)}</b> · ${esc(x.name)} ${esc(x.payload?.reason || x.payload?.status || x.payload?.error || "")}${x.payload?.ms != null ? " · " + x.payload.ms + "ms" : ""}</li>`).join("")}</ol>`;
}
function mealDetail(p) {
  if (!p["메뉴"])
    return `<p>${esc(p["안내"] || "먼저 조리한 음식을 활용해요.")}</p>${p["남은 음식 우선"] ? leftoverRows() : ""}<div class="btnbar">${btn("재료 추가", "lot", "btn", "plus")}${btn("메뉴 고르기", "recipes", "btn alt")}</div>${excluded(p)}`;
  const need = p["부족량(g)"] || {},
    unknown = p["수량 확인"] || [],
    n = p["영양"] || {};
  return `<span class="pill">${esc(p["상태"])}</span><p class="plan-name">${esc(p["메뉴"])}</p><p class="muted">${esc(p["판단 기준"])}</p>
 <div class="facts"><div class="fact"><small>조리시간</small><b>${p["조리시간(분)"]}<span>분</span></b></div><div class="fact"><small>예상 열량</small><b>${fmt(p["예상 kcal"])}<span> kcal</span></b></div><div class="fact"><small>단백질</small><b>${fmt(n.protein_g)}<span> g</span></b></div></div>
 <p class="hint">${p["늦어도 조리 시작"] ? "늦어도 " + esc(p["늦어도 조리 시작"]) + "에 조리를 시작하세요." : ""} ${esc(p["일정 안내"] || "")}</p><h3>1인분 재료</h3>${Object.entries(
   p["예시 1인분(g)"] || {},
 )
   .map(
     ([name, g]) =>
       `<div class="list-line"><strong>${esc(name)} · ${fmt(g)}g</strong>${need[name] ? btn(fmt(need[name]) + "g 장보기", "shopping", "chip", "shopping-bag", name) : pill(unknown.includes(name) ? "용량 확인" : "보유", unknown.includes(name))}</div>`,
   )
   .join("")}
 <h3 class="guide-head">조리 순서</h3><ol class="step-list">${(p["조리 단계"] || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ol><div class="btnbar">${btn("조리 모드", "cookMode", "btn", "timer", p["메뉴"])}${Object.keys(need).length ? btn("부족분 장바구니에 담기", "toCart", "btn alt", "shopping-bag") : btn("조리 기록", "cook", "btn alt", "cooking-pot")}${btn("영상 레시피", "videos", "btn alt", "circle-play", p["메뉴"])}${btn("일정 저장", "plans", "btn alt", "calendar-days")}</div>
 ${p["시간대"] ? `<p class="hint">${typed(p["시간대"])}</p>` : ""}${excluded(p)}<details><summary>영양 추정 근거</summary><p class="hint">${esc(p["근거"])} · 원물 기준 100g의 영양성분을 사용량에 맞춰 합산했어요. 제품과 조리법에 따라 달라질 수 있어요.</p>${(p["영양 출처"] || []).map((x) => a(x["재료"], x.url)).join(" · ")}</details>`;
}
function excluded(p) {
  return p["제외 후보"]?.length
    ? `<details><summary>다른 메뉴가 제외된 이유</summary>${p["제외 후보"].map((x) => `<p class="hint">${esc(x["메뉴"])} · ${esc(x["사유"])}</p>`).join("")}</details>`
    : "";
}
function showResult(msg, r) {
  const p = r["계획"];
  let content = "";
  if (p["자료"])
    content =
      Object.entries(p["자료"])
        .map(([k, v]) => `<h3 class="guide-head">${esc(labels[k] || k)}</h3>${provider(v)}`)
        .join("") +
      `<p class="guide-head">직접 검색</p><div class="btnbar">${Object.entries(p["직접 검색"] || {})
        .map(([k, u]) => a(k, u))
        .join(" · ")}</div>`;
  else if (p["주간"])
    content =
      '<p class="hint">현재 냉장고 기준 7일 초안입니다. 날짜별 실제 소진량은 조리 후 반영해요.</p>' +
      p["주간"]
        .map(
          (d) =>
            `<div class="list-line"><div><strong>${esc(d.day)} · ${esc(d.meal || "가능한 메뉴 없음")}</strong><small>${esc(d.workout)} · 추가할 재료 ${Object.keys(d.missing).length}종</small></div></div>`,
        )
        .join("");
  else if (p["조회"])
    content =
      provider(p["조회"]) +
      (msg.startsWith("레시피 ") && p["조회"].ok
        ? p["조회"].data
            .filter((x) => x.id && x["조리 순서"]?.length)
            .map((x) => btn(x["메뉴"] + " 조리 모드", "cookModeExt", "chip", "timer", x.id) + btn(x["메뉴"] + " 내 식단에 담기", "importRecipe", "chip", "plus", x.id))
            .join("")
        : "") +
      (p["안내"] ? `<p>${esc(p["안내"])}</p>` : "");
  else if (p["요청 메뉴"])
    content =
      `<h3>${esc(p["메뉴"] || p["요청 메뉴"])}</h3><p>${typed(p["필요 재료 원문"])}</p><ol class="step-list">${(p["조리 단계"] || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` +
      Object.entries(p)
        .filter(([, v]) => v && typeof v === "object" && "ok" in v)
        .map(([k, v]) => `<details><summary>${esc(k)}</summary>${provider(v)}</details>`)
        .join("");
  else if (p["예시 1인분(g)"] || p["남은 음식 우선"]) content = mealDetail(p);
  else content = `<p>${esc(p["안내"] || "반영했어요.")}</p>`;
  if (p["예산 안내"]) content += "<p class=hint>" + esc(p["예산 안내"]) + "</p>";
  sheet(
    msg,
    `<div class="result">${content}</div><details><summary>이번 실행 과정 (${r["추적"].length}단계)</summary>${trace(r["추적"])}</details>`,
  );
}
function field(label, name, type = "text", value = "", extra = "") {
  return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
}
function select(label, name, values, sel) {
  return `<label>${label}<select aria-label="${esc(label)}" name="${name}">${opts(values, sel)}</select></label>`;
}
function form(id, body, submit = "저장") {
  return `<form class="form" data-form="${id}">${body}<button class="btn" type="submit">${ic("check")}${submit}</button></form>`;
}
function settings() {
  const s = st["설정"],
    targets = s.targets || {};
  sheet(
    "나의 기준",
    form(
      "settings",
      `<div class="fields">${select("식단 기준", "diet", ["균형", "단백질 우선", "식물성"], s.diet)}${select("운동 목표", "goal", ["체력", "근력", "체중 관리"], s.goal)}</div>${field("제외 재료·알레르기 (쉼표로 구분)", "avoid", "text", (s.avoid || []).join(", "))}${field("먼저 쓸 재료", "priority", "text", s.priority || "")}<div class="fields">${select("운동 부위", "body", ["전신", "상체", "하체", "코어", "등", "어깨", "가슴", "팔"], s.body)}${select("숙련도", "level", ["초보", "중급", "숙련"], s.level)}${select("사용 기구", "gear", ["맨몸", "덤벨"], (s.gear || [])[0])}${field("식사·운동 총 가용시간(분)", "minutes", "number", s.minutes, 'min="1" max="240" required')}${field("운동 희망시간(분)", "exercise_minutes", "number", s.exercise_minutes || 10, 'min="5" max="120" required')}</div><div class="fields">${field("상품 1개 예산(원)", "budget_krw", "number", s.budget_krw || "", "min=0 max=10000000")}${field("자주 찾는 지역", "area", "text", s.area || "")}</div><h3>내가 정한 하루 목표</h3><div class="fields">${field("단백질(g)", "protein_g", "number", targets.protein_g, 'min="1" max="400"')}${field("수분(mL)", "water_ml", "number", targets.water_ml, 'min="1" max="10000"')}${field("식이섬유(g)", "fiber_g", "number", targets.fiber_g, 'min="1" max="100"')}</div>`,
    ),
  );
}
function chat() {
  sheet(
    "한끼 코치",
    form(
      "chat",
      `<label>무엇을 도와드릴까요?<textarea name="message" required placeholder="냉장고에 두부와 달걀이 있어. 20분 안에 뭘 먹을까?"></textarea></label><div class="chips">${["추천", "외식", "집밥", "주간계획", "일정조회 " + st["날짜"]].map((x) => btn(x, "prompt", "chip", "", x)).join("")}</div>`,
      "코치에게 보내기",
    ),
  );
}
async function planSheet(id = null) {
  plans = await api("/api/plans");
  const p = plans.find((x) => String(x.id) === String(id));
  const s = st["설정"].window || {};
  const cal = await api("/api/calendar/status");
  const planRows = plans.length
    ? plans
        .map(
          (x) =>
            `<div class="list-line"><div><strong>${esc(x.title)}</strong><small>${esc(x.trip_date)} · ${esc(x.start_time)}–${esc(x.end_time)}</small><div class="btnbar">${btn("변경", "planEdit", "chip", "", x.id)}${btn("캘린더 등록", "calReg", "chip", "", x.id)}${btn("삭제", "planDelete", "chip danger", "", x.id)}</div></div></div>`,
        )
        .join("")
    : '<p class="empty">저장한 일정이 없습니다.</p>';
  sheet(
    "계획과 일정",
    (cal.provider === "google"
      ? btn("Google 캘린더 연결 해제", "calDisconnect", "chip")
      : cal.oauth_available
        ? '<a class="chip" href="/api/calendar/connect">Google 캘린더 연결</a>'
        : '<p class="hint">이 기기의 로컬 캘린더 사용 중</p>') +
      form(
        "plan",
        `<input type="hidden" name="id" value="${esc(p?.id || "")}">${field("계획명", "title", "text", p?.title || st["계획"]["메뉴"] || "", 'required maxlength="100"')}${field("날짜", "trip_date", "date", p?.trip_date || st["날짜"], "required")}<div class="fields">${field("시작", "start_time", "time", p?.start_time || "18:00", "required")}${field("종료", "end_time", "time", p?.end_time || "18:30", "required")}</div>`,
        p ? "변경 저장" : "계획 저장",
      ) +
      `<div id="overlaps" role="status"></div><h3 class="guide-head">저장된 계획</h3>${planRows}<hr class="divider"><h3>일정을 고려한 추천</h3>` +
      form(
        "window",
        `<div class="fields">${field("기준일", "day", "date", s.day || st["날짜"], "required")}${field("시작 시각", "start", "time", s.start || "18:00", "required")}</div>`,
        "시간대 적용",
      ) +
      `<div class="btnbar">${btn("시간대 해제", "prompt", "chip", "", "시간대 해제")}${btn("오늘 일정 조회", "prompt", "chip", "", "일정조회 " + st["날짜"])}</div>`,
  );
}
async function logs() {
  const group = await api("/api/logs");
  sheet(
    "에이전트 실행 이력",
    group
      .map(
        (x) =>
          `<div class="list-line"><div><strong>${esc(x.session_id)}</strong><small>${x.events}개 이벤트 · 도구 ${x.tool_calls}회 · 재계획 ${x.replans}회</small></div>${btn("상세", "logDetail", "chip", "", x.session_id)}</div>`,
      )
      .join("") || '<p class="empty">아직 실행 기록이 없습니다.</p>',
  );
}
const action = {
  toCart: () =>
    sheet(
      "부족 재료 담기",
      form(
        "cart",
        field("만들 분량(인분)", "servings", "number", 1, "min=1 max=20 required") +
          '<p class="hint">필요량에서 현재 재고를 뺍니다. 같은 항목을 다시 담으면 더 큰 필요량을 유지해요.</p>',
        "장바구니에 담기",
      ),
    ),
  bought: (name) =>
    sheet(
      "구입 후 냉장고에 넣기",
      form(
        "bought",
        '<input type="hidden" name="name" value="' +
          esc(name) +
          '"><h3>' +
          esc(name) +
          "</h3>" +
          field("구입한 중량(g)", "quantity", "number", "", "min=0.01 step=0.01 required") +
          field("소비기한 (선택)", "expires", "date"),
        "냉장고에 넣기",
      ),
    ),
  uncart: (n) => send("장바구니삭제 " + n),
  importRecipe: (id) => {
    const m = last?.["계획"]?.["조회"]?.data?.find((x) => String(x.id) === String(id));
    if (!m) return;
    sheet(
      "내 식단에 레시피 담기",
      form(
        "importRecipe",
        "<p>" +
          esc(m["메뉴"]) +
          ' · 식품안전나라</p><p class="hint">' +
          esc(m["재료·분량"]) +
          '</p><input type="hidden" name="id" value="' +
          esc(id) +
          '">' +
          field("확인한 조리시간(분)", "minutes", "number", "", "min=1 max=600 required") +
          '<label>1인분 재료와 g (한 줄에 하나)<textarea name="portions" required placeholder="두부 100&#10;달걀 50"></textarea></label>',
      ),
    );
  },
  calDisconnect: async () => {
    await api("/api/calendar/connection", "DELETE");
    await planSheet();
  },
  close,
  settings,
  chat,
  plans: () => planSheet(),
  logs,
  meal: () => sheet("추천 식단", mealDetail(st["계획"])),
  week: () => send("주간계획", {}, true),
  featured: () => demoRecipe("두부 달걀찜"),
  lot: () =>
    sheet(
      "냉장고에 재료 추가",
      form(
        "lot",
        `${field("재료 이름", "name", "text", "", "required maxlength=50 placeholder='예: 두부'")}<div class="fields">${field("포장 용량 (선택)", "quantity", "number", "", "min=0.01 step=0.01 placeholder='미입력 가능'")}${select("단위", "unit", ["g", "kg", "개"], "g")}</div>${field("소비기한 (선택)", "expires", "date")}<p class="hint">달걀 1개는 약 50g으로 환산해요. 다른 재료는 포장의 중량을 적어 주세요.</p>`,
        "냉장고에 넣기",
      ),
    ),
  water: () =>
    sheet(
      "물 섭취 기록",
      form("water", field("마신 양(mL)", "amount", "number", 250, "min=1 max=2000 required"), "기록하기"),
    ),
  sleep: () =>
    sheet(
      "수면 기록",
      form(
        "sleep",
        field(
          "오늘의 수면 시간",
          "amount",
          "number",
          st["오늘 기록"].sleep_hours ?? "",
          "min=0 max=24 step=0.1 required",
        ),
        "기록하기",
      ),
    ),
  cook: () =>
    sheet(
      "조리 기록",
      form(
        "cook",
        `<p>${esc(st["계획"]["메뉴"])} · 소비기한이 가까운 포장부터 차감해요.</p><div class="fields">${field("만든 분량(인분)", "servings", "number", 1, "min=1 max=20 required")}${field("실제 조리시간(분)", "actual", "number", st["계획"]["조리시간(분)"], "min=1 max=600 required")}</div>${st["계획"]["수량 확인"]?.length ? `<label><span><input style="width:auto;min-height:auto" type="checkbox" required> 미계량 재료의 실제 분량을 확인했어요.</span></label>` : ""}`,
        "조리 완료",
      ),
    ),
  eat: (n) => send("섭취 " + n),
  shopping: (n) => send("쇼핑 " + n, {}, true),
  videos: (n) => send("영상 " + n, {}, true),
  choose: (n) => send("메뉴 " + n, {}, true),
  remove: (id) =>
    sheet(
      "포장 삭제",
      `<p>이 포장을 냉장고에서 삭제할까요?</p><div class="btnbar">${btn("삭제", "removeYes", "btn", "trash-2", id)}${btn("취소", "close", "btn alt")}</div>`,
    ),
  removeYes: (id) => send("포장삭제 " + id),
  prompt: (n) => send(n, {}, true),
  finish: () =>
    sheet(
      "운동 완료 기록",
      form(
        "finish",
        field(
          "실제 운동시간(분)",
          "minutes",
          "number",
          st["운동 계획"].minutes || 10,
          "min=1 max=240 required",
        ) + select("체감 난이도", "effort", ["쉬움", "적당함", "어려움"], "적당함"),
        "기록하기",
      ),
    ),
  health: () =>
    sheet(
      "건강 데이터 연결",
      '<p>Android 14 이상에서 Samsung Health 또는 Google Fit이 Health Connect에 기록하도록 설정해 주세요. 읽을 항목을 허용하고 오늘의 합계를 확인한 뒤 서버에 저장할 수 있어요.</p><p class="hint">가져온 항목은 같은 날 기기 합계를 우선 표시해요. 직접 기록한 양은 별도로 보관합니다.</p><div class="btnbar"><a class="btn" href="hankki://health">Android 앱에서 연결</a><a class="chip" href="/privacy">개인정보 안내</a><a class="chip" href="hankki://settings">앱 서버 설정</a></div>',
    ),
  planEdit: (id) => planSheet(id),
  calReg: (id) => send("일정등록 " + id, {}, true),
  planDelete: (id) =>
    sheet(
      "계획 삭제",
      `<p>저장한 계획을 삭제할까요? 이미 등록한 외부 캘린더 일정은 해당 캘린더에서 관리할 수 있어요.</p><div class="btnbar">${btn("계획 삭제", "planDeleteYes", "btn", "", id)}${btn("취소", "plans", "btn alt")}</div>`,
    ),
  planDeleteYes: async (id) => {
    await api("/api/plans/" + encodeURIComponent(id), "DELETE");
    await planSheet();
  },
  logDetail: async (id) => {
    let events = await api("/api/logs/" + encodeURIComponent(id));
    sheet("실행 상세", trace(events) + btn("이 세션 로그 삭제", "logDelete", "chip danger", "", id));
  },
  logDelete: (id) =>
    sheet(
      "실행 이력 삭제",
      `<p>이 대화의 에이전트 실행 이력을 삭제할까요?</p>${btn("로그 삭제", "logDeleteYes", "btn", "", id)}`,
    ),
  logDeleteYes: async (id) => {
    await api("/api/logs/" + encodeURIComponent(id), "DELETE");
    await logs();
  },
  erase: () =>
    sheet(
      "내 기록 삭제",
      form(
        "erase",
        "<p>이 기기의 냉장고·건강 기록·일정·실행 이력을 지웁니다.</p>" +
          field("확인을 위해 ‘삭제’를 입력하세요.", "confirm", "text", "", "required"),
        "내 기록 삭제",
      ),
    ),
};
function demoRecipe(title) {
  const m = catalog.meals.find((v) => v.title === title);
  sheet(
    "오늘의 레시피",
    `<p class="plan-name">${esc(title)}</p><p class="muted">1인분 · ${m.minutes}분</p><p class="guide-head">필요한 재료</p><p>${Object.entries(
      m.grams,
    )
      .map(([n, g]) => esc(n) + " " + g + "g")
      .join(
        " · ",
      )}</p><ol class="step-list">${m.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol><div class="btnbar">${btn("조리 모드", "cookMode", "btn", "timer", title)}${btn("내 재료와 비교", "choose", "btn alt", "refrigerator", title)}${btn("영상 레시피", "videos", "btn alt", "circle-play", title)}</div>`,
  );
}
const forms = {
  cart: (v) => send("장바구니담기", { servings: Number(v.servings) }),
  bought: (v) => send("구매완료 " + v.name, { quantity: Number(v.quantity), unit: "g", expires: v.expires }),
  importRecipe: async (v) => {
    const grams = {};
    for (const line of v.portions.trim().split(/\n/)) {
      const m = line.trim().match(/^(.+?)\s+(\d+(?:\.\d+)?)\s*g?$/);
      if (!m) throw Error("각 줄에 재료명과 g 수를 입력하세요.");
      grams[m[1]] = (grams[m[1]] || 0) + Number(m[2]);
    }
    const r = await send("레시피저장", { id: v.id, minutes: Number(v.minutes), grams }, true);
    if (r) {
      catalog = await api("/api/catalog");
      render();
    }
  },
  lot: (v) => send("입고", { ...v, quantity: v.quantity ? Number(v.quantity) : null }),
  water: (v) => send("물 " + v.amount),
  sleep: (v) => send("수면 " + v.amount),
  cook: (v) => send(`조리 ${v.servings}인분 ${v.actual}분`),
  finish: (v) => send("운동완료", { ...v, minutes: Number(v.minutes), body: st["운동 계획"].body }),
  settings: (v) => {
    const t = {};
    for (const k of ["water_ml", "protein_g", "fiber_g"]) {
      if (v[k]) t[k] = Number(v[k]);
      delete v[k];
    }
    return send("설정", {
      ...v,
      budget_krw: Number(v.budget_krw) || 0,
      avoid: v.avoid
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      gear: [v.gear],
      minutes: Number(v.minutes),
      exercise_minutes: Number(v.exercise_minutes),
      targets: t,
    });
  },
  source: (v, f) => send(f.dataset.cmd + " " + v.term.trim(), {}, true),
  chat: (v) => send(v.message, {}, true),
  window: (v) => send("시간대 " + v.day + " " + v.start, {}, true),
  plan: async (v) => {
    const id = v.id;
    delete v.id;
    const r = await api("/api/plans" + (id ? "/" + id : ""), id ? "PATCH" : "POST", v);
    await planSheet();
    $("#overlaps").textContent = r.overlaps.length
      ? "저장됨 · 겹치는 계획 " + r.overlaps.map((x) => x.title).join(", ")
      : "계획을 저장했어요.";
  },
  erase: async (v) => {
    await api("/api/data?confirm=" + encodeURIComponent(v.confirm), "DELETE");
    close();
    last = null;
    await start();
    note("기록을 삭제했어요.");
  },
};
window.importHealth = (v) => send("건강연동", v);
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-do]");
  if (!b) return;
  const name = b.dataset.do;
  if (busy && name !== "close") return;
  try {
    if (navs.some((n) => n[0] === name)) {
      close();
      go(name);
    } else if (action[name]) await action[name](b.dataset.arg);
  } catch (err) {
    note(err.message);
    markWaiting(err.message);
  }
});
document.addEventListener("submit", async (e) => {
  const f = e.target.closest("[data-form]");
  if (!f) return;
  e.preventDefault();
  if (busy) return;
  const b = f.querySelector('button[type="submit"],button:not([type])');
  if (b) b.disabled = true;
  try {
    await forms[f.dataset.form](fields(f), f);
  } catch (err) {
    note(err.message);
    markWaiting(err.message);
  } finally {
    if (b) b.disabled = false;
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "meal-filter") $("#meal-list").innerHTML = recipeList(e.target.value.trim());
});
dialog.addEventListener("click", (e) => {
  if (e.target === dialog) {
    const r = dialog.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) close();
  }
});
window.addEventListener("hashchange", () => {
  close();
  render();
  window.scrollTo(0, 0);
  $("#main").focus({ preventScroll: true });
});
async function start() {
  try {
    st = await api("/api/state");
    catalog = await api("/api/catalog");
    render();
  } catch (err) {
    $("#main").innerHTML =
      `<h1>연결이 필요해요</h1><p>${esc(err.message)}</p><button class="btn" onclick="location.reload()">다시 시도</button>`;
  }
}
start();
