"use strict";
// 물·영양제 알림: 기록 화면 카드 · 화면 안 배너 · 브라우저 알림 · Android 시스템 알림 예약
let remindItems = [];
const isAndroid = () => !!window.HankkiReminder;
const shownKey = "hk-reminder-shown";

function remindCard() {
  if (!remindItems.length)
    return `<p class="muted">물이나 영양제 알림을 만들어 보세요. "비타민D 아침 9시에 알려줘"처럼 Agent 에게 말해도 돼요.</p>`;
  return remindItems
    .map((r) => {
      const head = r.kind === "water"
        ? `<strong>💧 물 마시기</strong><small>${esc(r.start)}~${esc(r.end)} · ${r.every_min / 60}시간마다 · 한 컵 ${r.cup_ml}mL · 오늘 ${fmt(r.drank_ml)} / 목표 ${fmt(r.target_ml)}mL (지금 진도 ${fmt(r.expected_ml)}mL)</small>`
        : `<strong>💊 ${esc(r.title)}</strong><small>${r.dose ? esc(r.dose) + " · " : ""}${r.times.map((t) => (r.taken.includes(t) ? "✓ " : "") + t).join(" · ")}</small>`;
      return `<div class="list-line ${r.enabled ? "" : "off"}"><div>${head}<div class="btnbar">${r.kind === "supplement" ? btn("먹었어요", "remindTake", "chip", "check", r.id) : btn("한 컵 마셨어요", "remindDrink", "chip", "droplet", r.cup_ml)}${btn(r.enabled ? "끄기" : "켜기", "remindToggle", "linkbtn", "", r.id)}${btn("삭제", "remindDelete", "linkbtn", "", r.id)}</div></div>${r.next ? pill("다음 " + r.next) : ""}</div>`;
    })
    .join("");
}
function remindPermission() {
  if (isAndroid() || !("Notification" in window)) return "";
  if (Notification.permission === "granted") return '<p class="hint">브라우저 알림이 켜져 있어요. 이 화면이 열려 있을 때 알려 드려요.</p>';
  return btn("브라우저 알림 켜기", "remindAllow", "btn alt", "sparkles");
}
async function loadReminders() {
  try {
    remindItems = (await api("/api/reminders")).items;
  } catch {
    return;
  }
  const box = $("#reminders");
  if (box) box.innerHTML = remindCard() + `<div class="btnbar">${btn("물 알림", "remindWater", "btn", "droplet")}${btn("영양제 알림", "remindPill", "btn alt", "plus")}${remindPermission()}</div><p class="footnote">물은 목표 대비 진도보다 덜 마셨을 때만, 영양제는 아직 안 먹었을 때만 알려요. 복용량은 제품 표시나 전문가 안내를 따르세요.${isAndroid() ? " 앱이 꺼져 있어도 알림이 와요." : " 화면을 닫으면 웹 알림은 오지 않아요(앱에서는 와요)."}</p>`;
  if (isAndroid()) window.HankkiReminder.schedule(JSON.stringify(remindItems));
}
function banner(d) {
  let el = $("#reminder-banner");
  if (!el) {
    el = document.createElement("div");
    el.id = "reminder-banner";
    el.setAttribute("role", "alert");
    document.body.appendChild(el);
  }
  el.innerHTML = `<div><strong>${esc(d.title)}</strong><p>${esc(d.body)}</p></div><div class="btnbar">${btn(d.action.label, "remindDo", "btn", "check", d.action.message)}${btn("닫기", "remindClose", "linkbtn")}</div>`;
  el.classList.add("on");
}
async function checkDue() {
  if (document.hidden && isAndroid()) return; // 앱이 뒤에 있으면 시스템 알림이 맡는다
  let due;
  try {
    due = (await api("/api/reminders/due")).due;
  } catch {
    return;
  }
  let shown = {};
  try {
    shown = JSON.parse(localStorage.getItem(shownKey) || "{}");
  } catch {}
  const today = st?.["날짜"] || "";
  for (const d of due) {
    const k = today + d.id + d.slot;
    if (shown[k]) continue;
    shown[k] = 1;
    banner(d);
    if (!isAndroid() && "Notification" in window && Notification.permission === "granted") {
      const n = new Notification(d.title, { body: d.body, icon: "/static/mark.svg", tag: d.id + d.slot });
      n.onclick = () => {
        window.focus();
        go("journal");
      };
    }
  }
  try {
    localStorage.setItem(shownKey, JSON.stringify(Object.fromEntries(Object.entries(shown).filter(([k]) => k.startsWith(today)))));
  } catch {}
}
const _renderBase = render;
render = function () {
  _renderBase();
  if (route() === "journal") loadReminders();
};
async function remindSend(message, params = {}) {
  await send(message, params, false);
  await loadReminders();
}
Object.assign(action, {
  remindWater: () =>
    sheet(
      "물 알림",
      form(
        "remindWater",
        `<div class="fields">${field("시작", "start", "time", "09:00", "required")}${field("끝", "end", "time", "21:00", "required")}</div>${select("간격", "every", ["1시간", "1시간 30분", "2시간", "3시간"], "2시간")}${field("한 번에 마실 양(mL)", "cup", "number", 250, "min=50 max=1000 required")}<p class="hint">하루 목표는 설정의 수분 목표(없으면 1,500mL)를 써요. 목표 진도보다 앞서 있으면 알림을 건너뛰어요.</p>`,
        "알림 만들기",
      ),
    ),
  remindPill: () =>
    sheet(
      "영양제 알림",
      form(
        "remindPill",
        `${field("이름", "name", "text", "", "required maxlength=30 placeholder='예: 비타민D'")}${field("복용량 메모 (선택)", "dose", "text", "", "maxlength=30 placeholder='제품 표시대로 적어 주세요'")}<div class="fields">${field("시각 1", "t1", "time", "09:00", "required")}${field("시각 2 (선택)", "t2", "time")}${field("시각 3 (선택)", "t3", "time")}</div><p class="hint">한끼는 복용량을 권하지 않아요. 제품 표시나 의사·약사 안내를 따르세요.</p>`,
        "알림 추가",
      ),
    ),
  remindTake: (id) => remindSend("영양제복용 " + id),
  remindDrink: (ml) => remindSend("물 " + ml),
  remindToggle: (id) => remindSend("알림토글 " + id),
  remindDelete: (id) => remindSend("알림삭제 " + id),
  remindAllow: async () => {
    const p = await Notification.requestPermission();
    note(p === "granted" ? "브라우저 알림을 켰어요." : "알림이 허용되지 않았어요. 브라우저 설정에서 바꿀 수 있어요.");
    loadReminders();
  },
  remindDo: async (message) => {
    $("#reminder-banner")?.classList.remove("on");
    await remindSend(message);
  },
  remindClose: () => $("#reminder-banner")?.classList.remove("on"),
});
Object.assign(forms, {
  remindWater: (v) =>
    remindSend("알림추가", { kind: "water", start: v.start, end: v.end, every_min: { "1시간": 60, "1시간 30분": 90, "2시간": 120, "3시간": 180 }[v.every], cup_ml: Number(v.cup) }),
  remindPill: (v) => remindSend("알림추가", { kind: "supplement", name: v.name, dose: v.dose, times: [v.t1, v.t2, v.t3].filter(Boolean) }),
});
setInterval(checkDue, 60_000);
setTimeout(checkDue, 4000);
setTimeout(() => isAndroid() && loadReminders(), 2500);
