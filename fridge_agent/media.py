"""조리 미디어: 단계 사진 중계·캐시, 깊이 맵(2.5D 움직임), 검수 승인된 AI 조리 클립.

- 사진은 허용한 공공 제공처(식품안전나라)에서만 받아 서버에 캐시한다. 같은 출처로 내려보내야
  WebGL 이 사진을 텍스처로 쓸 수 있고, 앱(WebView)의 혼합 콘텐츠 차단도 피한다.
- 깊이 맵은 media_tools/make_depth.py 가 미리 만든 파일이 있을 때만 쓴다.
- AI 클립은 media_tools/make_clips.py 로 만든 뒤 사람이 approved=true 로 바꾼 것만 내보낸다.
"""

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

ALLOWED_HOSTS = ("foodsafetykorea.go.kr",)
# 운동 시연 사진: free-exercise-db (Unlicense, 퍼블릭 도메인) 저장소의 이미지 경로만 허용
ALLOWED_PREFIXES = ("https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/",)
MAX_BYTES = 4_000_000
TYPES = {b"\xff\xd8": ("jpg", "image/jpeg"), b"\x89PNG": ("png", "image/png"), b"RIFF": ("webp", "image/webp"), b"GIF8": ("gif", "image/gif")}


def root():
    path = Path(os.getenv("FRIDGE_DATA_DIR", ".")) / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def allowed(url):
    if any((url or "").startswith(p) and ".." not in url for p in ALLOWED_PREFIXES):
        return True
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def key(text):
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def cached(url):
    """캐시된 사진 경로와 형식. 없으면 받아서 저장한다. 허용하지 않은 주소는 ValueError."""
    if not allowed(url):
        raise ValueError("허용하지 않은 사진 주소입니다.")
    name = key(url)
    for ext, mime in TYPES.values():
        path = root() / f"{name}.{ext}"
        if path.exists():
            return path, mime
    req = Request(url, headers={"User-Agent": "Hankki/1.0 (github.com/0Ju12/ai-agents)"})
    with urlopen(req, timeout=8) as res:
        if not allowed(res.geturl()):
            raise ValueError("허용하지 않은 주소로 이동했습니다.")
        body = res.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("사진이 너무 큽니다.")
    kind = next((v for sig, v in TYPES.items() if body.startswith(sig)), None)
    if not kind:
        raise ValueError("사진 형식이 아닙니다.")
    path = root() / f"{name}.{kind[0]}"
    path.write_bytes(body)
    return path, kind[1]


def proxied(url):
    return "/api/media?u=" + quote(url, safe="") if allowed(url) else None


def depth_path(url):
    path = root() / f"{key(url)}.depth.png"
    return path if path.exists() else None


def depth_url(url):
    return "/api/media/depth?u=" + quote(url, safe="") if url and allowed(url) and depth_path(url) else None


# ── AI 조리 클립 (사람이 승인한 것만) ─────────────────────────
def manifest_path():
    return root() / "clips.json"


def manifest():
    try:
        return json.loads(manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_manifest(data):
    manifest_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clip_file(recipe, step):
    entry = manifest().get(key(recipe), {}).get(str(step))
    if not entry or entry.get("approved") is not True:
        return None
    path = root() / "clips" / entry["file"]
    return path if path.exists() and path.parent == root() / "clips" else None


def clip_url(recipe, step):
    return f"/api/media/clip/{key(recipe)}/{step}" if clip_file(recipe, step) else None


def clip_by_key(recipe_key, step):
    entry = manifest().get(recipe_key, {}).get(str(step))
    if not entry or entry.get("approved") is not True:
        return None
    path = root() / "clips" / Path(entry["file"]).name
    return path if path.exists() else None


def decorate(guide, recipe):
    """조리 가이드 카드에 중계 사진·깊이 맵·승인 클립 주소를 붙인다."""
    for card in guide["단계"]:
        original = card.get("사진")
        card["사진"] = proxied(original) if original else None
        card["깊이"] = depth_url(original) if original else None
        card["클립"] = clip_url(recipe, card["순서"])
    if guide.get("대표 사진"):
        guide["대표 사진"] = proxied(guide["대표 사진"])
    return guide
