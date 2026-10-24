"""Downloads the two face models of the identity check (F7) into backend/models/face (or FACE_MODEL_DIR).

    python scripts/download_face_models.py

The files come from the OpenCV model zoo on GitHub and are checked with their SHA-256, so a broken or changed
download is never used. Docker runs this when the backend image is built. The files are not committed (37 MB).
"""
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
MODELS = {   # file name: (place in the model zoo, SHA-256)
    "face_detection_yunet_2023mar.onnx": (
        "face_detection_yunet", "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": (
        "face_recognition_sface", "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}


def main() -> int:
    """Downloads each model that is missing or changed, checks its SHA-256, and saves it."""
    folder = Path(os.getenv("FACE_MODEL_DIR", "models/face"))
    if not folder.is_absolute():
        folder = Path(__file__).resolve().parents[1] / folder
    folder.mkdir(parents=True, exist_ok=True)
    for name, (place, sha256) in MODELS.items():
        target = folder / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
            print(f"ok       {name}")
            continue
        print(f"download {name} ...")
        data = urllib.request.urlopen(f"{BASE}/{place}/{name}", timeout=120).read()
        if hashlib.sha256(data).hexdigest() != sha256:
            print(f"ERROR: {name} has the wrong checksum; it was not saved.")
            return 1
        target.write_bytes(data)
        print(f"saved    {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
