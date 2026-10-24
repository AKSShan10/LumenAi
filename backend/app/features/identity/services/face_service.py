"""Face recognition with OpenCV (F7). Runs on this server only: no AI service and no internet are used.

    face_vector(image_bytes)   finds the face in a picture and turns it into 128 numbers (a "face vector")
    similarity(a, b)           how alike two face vectors are (cosine similarity, -1 to 1)
    engine_problem()           why the face check cannot run (the model files are missing), "" when it can

Two small models from the OpenCV model zoo (scripts/download_face_models.py puts them in FACE_MODEL_DIR):
    YuNet  finds faces in a picture                  face_detection_yunet_2023mar.onnx    (0.2 MB)
    SFace  turns one face into a vector of 128 numbers  face_recognition_sface_2021dec.onnx  (37 MB)
Two pictures of the same person give similar vectors. OpenCV's own guide for SFace: cosine similarity of 0.363
or more means "the same person".

Only the vector is used to compare. It says nothing about age, gender, mood or looks, and nothing like that is
ever measured. Face recognition is less accurate in poor light and for some groups of people, so the result only
helps the interviewer, who always makes the final decision.
"""
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.core import config

log = logging.getLogger("face")

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"
SAME_PERSON = 0.363              # OpenCV's threshold for SFace: at least this similarity = the same person
CONFIDENT = 0.45                 # at least this = a confident match; between the two = low confidence
MIN_FACE_SCORE = 0.8             # how sure YuNet must be that it found a face
MAX_SIDE = 1280                  # big photos are made smaller first (faster, same result)


class FaceProblem(Exception):
    """The picture cannot be used. The code is one of: unreadable | no_face | several_faces | engine_missing."""
    def __init__(self, code: str, message: str):
        """Keeps the short code (e.g. no_face) next to the plain message."""
        super().__init__(message)
        self.code = code


def _model_dir() -> Path:
    """The folder with the two model files: FACE_MODEL_DIR, inside backend/ unless it is a full path."""
    path = Path(config.FACE_MODEL_DIR)
    return path if path.is_absolute() else Path(__file__).resolve().parents[4] / path


def engine_problem() -> str:
    """Why the face check cannot run (a model file is missing), or "" when it can."""
    missing = [name for name in (DETECTOR_FILE, RECOGNIZER_FILE) if not (_model_dir() / name).is_file()]
    if missing:
        return ("The face models are missing. Run: python scripts/download_face_models.py "
                "(Docker downloads them when the image is built).")
    return ""


@lru_cache(maxsize=1)
def _models():
    """Loads the two models once (the first face check takes a moment, later ones are fast)."""
    import cv2                                        # loaded only when a face check runs
    detector = cv2.FaceDetectorYN.create(str(_model_dir() / DETECTOR_FILE), "", (320, 320), MIN_FACE_SCORE)
    recognizer = cv2.FaceRecognizerSF.create(str(_model_dir() / RECOGNIZER_FILE), "")
    return cv2, detector, recognizer


def face_vector(image_bytes: bytes, allow_several: bool = False) -> list[float]:
    """The face vector of the one face in the picture. allow_several: use the biggest face (a camera frame).
    Raises FaceProblem when no single face can be used."""
    problem = engine_problem()
    if problem:
        raise FaceProblem("engine_missing", problem)
    cv2, detector, recognizer = _models()
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)   # the file bytes → a picture
    if image is None:
        raise FaceProblem("unreadable", "The picture could not be read (use a JPG or PNG photo).")
    scale = MAX_SIDE / max(image.shape[:2])
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale)
    detector.setInputSize((image.shape[1], image.shape[0]))   # YuNet needs the size of this picture
    _, faces = detector.detect(image)                 # one row per face: the box, 5 points and a score
    if faces is None or len(faces) == 0:
        raise FaceProblem("no_face", "No face was found in the picture.")
    if len(faces) > 1 and not allow_several:
        raise FaceProblem("several_faces", f"{len(faces)} faces were found; the photo must show one person.")
    biggest = max(faces, key=lambda face: face[2] * face[3])          # width x height of the face box
    # alignCrop cuts the face out and turns it straight; feature() turns it into 128 numbers
    vector = recognizer.feature(recognizer.alignCrop(image, biggest))
    return [round(float(v), 6) for v in vector.flatten()]


def similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two face vectors: 1 = the same picture, about 0 = two different people."""
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    norm = float(np.linalg.norm(va) * np.linalg.norm(vb))      # the lengths of both vectors (0 = an empty vector)
    return round(float(va @ vb) / norm, 3) if norm else 0.0
