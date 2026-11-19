"use strict";
// 첫 실행 튜토리얼: 앱이 하는 일과 사용 순서를 5장으로 안내한다. 위쪽 ? 버튼으로 다시 볼 수 있다.
const TOUR_KEY = "hk-onboarded-v1";
const TOUR = [
  { icon: "🥗", title: "한끼에 오신 걸 환영해요", body: "냉장고 재료의 양과 소비기한을 기준으로 오늘 먹을 메뉴, 장보기, 운동, 물·영양제 알림까지 한 곳에서 챙겨 드려요.", points: ["110가지 레시피에서 메뉴 추천", "부족한 재료만 장바구니에", "부위·강도별 운동 루틴"] },
  { icon: "🧊", title: "냉장고를 채워 두었어요", body: "처음 써 보실 수 있게 소비기한이 제각각인 예시 재료를 넣었어요. 냉장고 탭에서 지우거나 내 재료로 바꾸세요.", points: ["재료 추가: 이름만 써도 돼요", "사진·바코드로 등록", "‘예시 재료로 채우기’로 다시 채우기"] },
  { icon: "💬", title: "코치에게 상황을 말해 보세요", body: "가운데 코치 탭에서 지금 상황을 말하면 메뉴를 고르고, 부족한 재료 담기·조리 안내·영상까지 이어서 진행해요. 한 일은 되돌릴 수 있어요.", points: ["“퇴근했는데 20분밖에 없어. 단백질 위주로”", "“둘이 먹을 거고 있는 재료로만”", "“다른 후보 알려줘”"] },
  { icon: "🍳", title: "조리 모드 · 운동 모드", body: "조리 모드는 단계마다 장면 애니메이션과 타이머, 음성 안내를 보여 줘요. 운동 모드는 동작 애니메이션과 세트·휴식 타이머로 따라 하게 해 줘요.", points: ["‘크게 보기’로 전체 화면", "‘읽어주기’로 음성 안내", "YouTube 영상은 화면 안에서 재생"] },
  { icon: "🔔", title: "기록과 알림", body: "물·수면·식사를 기록하고 물·영양제 알림을 받을 수 있어요. “비타민D 아침 9시에 알려줘”처럼 코치에게 말해도 돼요.", points: ["일반 생활 참고 정보예요", "질환·치료는 의료진과 상의하세요", "데이터는 기록 탭에서 내려받기·삭제"] },
];
let tourAt = 0;
function tourCard() {
  const t = TOUR[tourAt],
    last = tourAt === TOUR.length - 1;
  return `<div class="tour-card" role="dialog" aria-modal="true" aria-labelledby="tour-title">
    <button class="iconbtn tour-skip" data-do="tourEnd" aria-label="튜토리얼 닫기">×</button>
    <div class="tour-icon" aria-hidden="true">${t.icon}</div>
    <h2 id="tour-title">${esc(t.title)}</h2><p>${esc(t.body)}</p>
    <ul>${t.points.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <div class="tour-dots" aria-label="${tourAt + 1} / ${TOUR.length}">${TOUR.map((_, i) => `<i class="${i === tourAt ? "on" : ""}"></i>`).join("")}</div>
    <div class="tour-nav">${tourAt ? btn("이전", "tourPrev", "btn alt") : btn("건너뛰기", "tourEnd", "btn alt")}${last ? btn("코치에게 말해 보기", "tourCoach", "btn", "sparkles") : btn("다음", "tourNext", "btn", "chevron-right")}</div></div>`;
}
function tourShow(i = 0) {
  tourAt = i;
  let el = $("#tour");
  if (!el) {
    el = document.createElement("div");
    el.id = "tour";
    document.body.appendChild(el);
  }
  el.innerHTML = tourCard();
  el.classList.add("on");
  el.querySelector(".tour-nav .btn:last-child")?.focus();
}
function tourEnd() {
  $("#tour")?.classList.remove("on");
  try {
    localStorage.setItem(TOUR_KEY, "1");
  } catch {}
}
Object.assign(action, {
  tour: () => tourShow(0),
  tourNext: () => tourShow(Math.min(TOUR.length - 1, tourAt + 1)),
  tourPrev: () => tourShow(Math.max(0, tourAt - 1)),
  tourEnd,
  tourCoach: () => {
    tourEnd();
    go("agent");
  },
});
document.addEventListener("keydown", (e) => {
  if (!$("#tour.on")) return;
  if (e.key === "Escape") tourEnd();
  if (e.key === "ArrowRight") action.tourNext();
  if (e.key === "ArrowLeft") action.tourPrev();
});
setTimeout(() => {
  let seen = false;
  try {
    seen = localStorage.getItem(TOUR_KEY) === "1";
  } catch {}
  if (!seen && !navigator.webdriver) tourShow(0);
}, 900);
