"use strict";
// 건강 체크(인바디·건강검진): 공개 기준과 비교한 참고 결과와 생활 안내. 진단이 아니다.
let healthLast = null;
async function loadHealth() {
  try {
    healthLast = await api("/api/health/latest");
  } catch {
    return;
  }
  const box = $("#health-card");
  if (box) box.innerHTML = healthSummary();
}
function levelPill(r) {
  return `<span class="pill ${r["수준"] === "높음" ? "danger" : r["수준"] === "주의" ? "warn" : ""}">${esc(r["판정"])}</span>`;
}
function healthSummary() {
  const h = healthLast;
  if (!h || !h["있음"])
    return `<p class="muted">인바디나 건강검진 수치를 넣으면 공개 기준과 비교해 생활 습관을 안내하고, 식단·운동 추천에 반영할 수 있어요.</p><div class="actions">${btn("수치 입력", "healthForm", "btn", "heart-pulse")}</div>`;
  const flagged = h["결과"].filter((r) => r["수준"] === "높음" || r["수준"] === "주의");
  return `<p class="hint">${esc(h["날짜"])} 입력 · 확인할 항목 ${flagged.length}개</p>${flagged.slice(0, 4).map((r) => `<div class="list-line"><div><strong>${esc(r["항목"])} ${esc(String(r["값"]))}${esc(r["단위"])}</strong></div>${levelPill(r)}</div>`).join("")}
    ${h["반영됨"]?.length ? `<p class="hint">식단 추천에 반영 중 · ${h["반영됨"].map((k) => ({ weight: "열량", sodium: "나트륨", sugar: "탄수화물", fat: "지방" })[k]).join("·")} 낮은 메뉴 우선</p>` : ""}
    <div class="btnbar">${btn("결과 보기", "healthResult", "btn alt", "notebook-text")}${btn("다시 입력", "healthForm", "btn alt", "heart-pulse")}</div>`;
}
function healthResultBody(h) {
  return `${h["진료 권유"].length ? `<div class="how-box danger-box">${h["진료 권유"].map((x) => `<p>⚠️ ${esc(x)}</p>`).join("")}</div>` : ""}
    <div class="health-table">${h["결과"].map((r) => `<div class="list-line"><div><strong>${esc(r["항목"])} · ${esc(String(r["값"]))}${esc(r["단위"])}</strong><small>${esc(r["참고 범위"])}</small></div>${levelPill(r)}</div>`).join("")}</div>
    ${h["생활 안내"].length ? `<p class="sec-label">생활 습관 안내</p><ul class="tips">${h["생활 안내"].map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : '<p>입력한 수치는 참고 범위 안에 있어요. 지금처럼 꾸준히 관리해요.</p>'}
    <div class="cta">${h["반영할 설정"].length ? (h["반영됨"]?.length ? btn("반영 해제", "healthUnapply", "btn alt") : btn("식단·운동 추천에 반영", "healthApply", "btn", "check")) : ""}</div>
    <details><summary>기준 출처</summary><ul>${h["기준 출처"].map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details><p class="footnote">${esc(h["안내"])}</p>`;
}
Object.assign(action, {
  healthForm: () => {
    const v = healthLast?.["입력"] || {};
    const num = (label, name, unit, extra) => field(`${label} (${unit})`, name, "number", v[name] ?? "", `step=any ${extra}`);
    sheet(
      "건강 체크 입력",
      form(
        "health",
        `<p class="hint">아는 값만 넣어도 돼요. 인바디·건강검진 결과지의 숫자를 그대로 옮겨 주세요.</p>
        ${select("성별", "sex", ["", "남", "여"], v.sex || "")}
        <p class="sec-label">신체 · 인바디</p><div class="fields">${num("키", "height_cm", "cm", "min=100 max=230")}${num("체중", "weight_kg", "kg", "min=25 max=300")}</div>
        <div class="fields">${num("체지방률", "body_fat_pct", "%", "min=3 max=70")}${num("골격근량", "muscle_kg", "kg", "min=5 max=80")}</div>${num("허리둘레", "waist_cm", "cm", "min=40 max=200")}
        <p class="sec-label">혈압 · 혈당</p><div class="fields">${num("수축기 혈압", "sbp", "mmHg", "min=60 max=260")}${num("이완기 혈압", "dbp", "mmHg", "min=30 max=160")}</div>${num("공복혈당", "glucose", "mg/dL", "min=40 max=500")}
        <p class="sec-label">콜레스테롤</p><div class="fields">${num("총콜레스테롤", "total_chol", "mg/dL", "min=60 max=500")}${num("LDL", "ldl", "mg/dL", "min=20 max=400")}</div><div class="fields">${num("HDL", "hdl", "mg/dL", "min=10 max=150")}${num("중성지방", "tg", "mg/dL", "min=20 max=3000")}</div>
        <p class="footnote">입력한 수치는 이 기기의 한끼 서버에만 저장돼요. 진단이 아닌 참고 정보예요.</p>`,
        "기준과 비교하기",
      ),
    );
  },
  healthResult: () => healthLast?.["있음"] && sheet("건강 체크 결과", healthResultBody(healthLast)),
  healthApply: async () => {
    await send("건강반영", {}, false);
    await loadHealth();
    sheet("건강 체크 결과", healthResultBody(healthLast));
    note("식단·운동 추천에 반영했어요.");
  },
  healthUnapply: async () => {
    await send("건강반영해제", {}, false);
    await loadHealth();
    sheet("건강 체크 결과", healthResultBody(healthLast));
  },
});
Object.assign(forms, {
  health: async (v) => {
    const params = { sex: v.sex || "" };
    for (const [k, x] of Object.entries(v)) if (k !== "sex" && x !== "") params[k] = Number(x);
    const r = await api("/api/chat", "POST", { message: "건강체크", params, request_id: uid() });
    st = { ...r, 계획: r["현재 추천"] };
    await loadHealth();
    sheet("건강 체크 결과", healthResultBody(healthLast));
  },
});
const _renderHealth = render;
render = function () {
  _renderHealth();
  if (route() === "journal") loadHealth();
};
