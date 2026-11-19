"""AI 조리 클립(사진 → 3~5초 영상)을 미리 만들고, 사람이 검수해 승인한 것만 앱에 보인다.

생성 모델은 손 모양·재료가 실제와 달라질 수 있어 자동 공개하지 않는다.
manifest(FRIDGE_DATA_DIR/media/clips.json) 의 approved 가 true 인 클립만 /api/media/clip 이 내보낸다.

    # 1) 생성 (사진은 조리 모드에서 열어 캐시된 것)
    python -m media_tools.make_clips make --recipe "kr:77" --step 2 --photo-url "https://www.foodsafetykorea.go.kr/..." --action 볶기
    # 2) 확인 후 승인 / 거절
    python -m media_tools.make_clips list
    python -m media_tools.make_clips approve --recipe "kr:77" --step 2
    python -m media_tools.make_clips reject --recipe "kr:77" --step 2

생성 제공처는 환경변수로 고른다 (키는 .env 에만):
    CLIP_PROVIDER=http     CLIP_API_URL=<이미지→영상 API 주소>  CLIP_API_KEY=<키>
      요청: POST {"image": data URL, "prompt": 문장, "seconds": 4} → 응답 {"video_url": "..."} 또는 mp4 본문
    CLIP_PROVIDER=command  CLIP_COMMAND="python my_wan_i2v.py --image {image} --prompt {prompt} --out {out}"
      (GPU 서버에서 Wan2.x · CogVideoX 같은 오픈소스 image-to-video 를 직접 돌릴 때)
식품안전나라 사진으로 영상을 만들어 공개하기 전에 이용 조건(2차 저작물 허용 여부)을 확인한다.
"""

import argparse
import base64
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import media  # noqa: E402

PROMPT = "실제 주방에서 사람이 '{action}' 동작을 하는 짧은 조리 장면. 사진 속 재료와 그릇을 그대로 유지하고, 새 재료를 추가하지 않는다. 카메라는 고정."


def generate(image_path, prompt, out):
    provider = os.getenv("CLIP_PROVIDER", "")
    if provider == "http":
        mime = "image/png" if image_path.suffix == ".png" else "image/jpeg"
        data = "data:" + mime + ";base64," + base64.b64encode(image_path.read_bytes()).decode()
        req = Request(
            os.environ["CLIP_API_URL"],
            data=json.dumps({"image": data, "prompt": prompt, "seconds": 4}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["CLIP_API_KEY"]},
        )
        with urlopen(req, timeout=600) as res:
            body = res.read(200_000_001)
            if res.headers.get_content_type() == "application/json":
                with urlopen(json.loads(body)["video_url"], timeout=600) as video:
                    body = video.read(200_000_001)
        out.write_bytes(body)
    elif provider == "command":
        cmd = os.environ["CLIP_COMMAND"].format(image=shlex.quote(str(image_path)), prompt=shlex.quote(prompt), out=shlex.quote(str(out)))
        subprocess.run(shlex.split(cmd), check=True, timeout=3600)
    else:
        sys.exit("CLIP_PROVIDER 를 http 또는 command 로 설정하세요.")
    if not out.exists() or out.stat().st_size < 1000:
        sys.exit("영상 파일이 만들어지지 않았습니다.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["make", "list", "approve", "reject"])
    parser.add_argument("--recipe")
    parser.add_argument("--step", type=int)
    parser.add_argument("--photo-url")
    parser.add_argument("--action", default="조리")
    a = parser.parse_args()
    data = media.manifest()
    if a.command == "list":
        for k, steps in data.items():
            for step, e in sorted(steps.items(), key=lambda x: int(x[0])):
                print(f"{e.get('recipe')} #{step}  {'승인' if e.get('approved') else '검수 대기'}  {e['file']}  {e.get('provider')}")
        return
    if not a.recipe or not a.step:
        sys.exit("--recipe 와 --step 을 지정하세요.")
    k, step = media.key(a.recipe), str(a.step)
    if a.command in {"approve", "reject"}:
        if step not in data.get(k, {}):
            sys.exit("해당 클립이 없습니다.")
        data[k][step]["approved"] = a.command == "approve"
        data[k][step]["reviewed"] = datetime.now().isoformat(timespec="seconds")
        media.save_manifest(data)
        print(a.command, a.recipe, step)
        return
    image, _ = media.cached(a.photo_url or "")
    folder = media.root() / "clips"
    folder.mkdir(exist_ok=True)
    out = folder / f"{k}-{step}.mp4"
    generate(image, PROMPT.format(action=a.action), out)
    data.setdefault(k, {})[step] = {
        "recipe": a.recipe,
        "file": out.name,
        "approved": False,  # 사람이 확인하기 전에는 공개하지 않는다
        "provider": os.getenv("CLIP_PROVIDER"),
        "created": datetime.now().isoformat(timespec="seconds"),
        "source_photo": a.photo_url,
    }
    media.save_manifest(data)
    print("검수 대기로 저장:", out)


if __name__ == "__main__":
    main()
