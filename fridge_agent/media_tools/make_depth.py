"""단계 사진의 깊이 맵을 미리 만든다 → 조리 모드에서 2.5D 움직임(WebGL)으로 쓴다.

서버 실행에는 필요 없는 선택 도구라 requirements.txt 에 넣지 않았다. 별도 환경에서:

    pip install transformers torch pillow
    python -m media_tools.make_depth            # FRIDGE_DATA_DIR/media 의 캐시 사진 전부
    python -m media_tools.make_depth --limit 20

모델: Depth Anything V2 Small (Apache-2.0). CPU 로도 사진 한 장에 수 초 걸린다.
사진은 조리 모드에서 한 번 열어 /api/media 캐시에 들어온 것만 처리한다.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import media  # noqa: E402

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        from PIL import Image
        from transformers import pipeline
    except ImportError:
        sys.exit("pip install transformers torch pillow 후 다시 실행하세요.")
    estimate = pipeline("depth-estimation", model=MODEL)
    photos = [p for p in sorted(media.root().iterdir()) if p.suffix in {".jpg", ".png", ".webp"} and ".depth" not in p.name]
    done = 0
    for photo in photos:
        target = photo.with_name(photo.stem + ".depth.png")
        if target.exists() and not args.force:
            continue
        depth = estimate(Image.open(photo).convert("RGB"))["depth"]  # 가까울수록 밝다
        depth.convert("L").resize(Image.open(photo).size).save(target)
        done += 1
        print("depth", photo.name)
        if args.limit and done >= args.limit:
            break
    print(f"{done}장 처리")


if __name__ == "__main__":
    main()
