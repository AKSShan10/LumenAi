"""Candidate identification (F7): the face in the call is compared with the photo from the application.
The face engine is replaced by made-up face vectors here (no real faces in the tests). The last test runs the real
OpenCV models on two public-domain pictures from scikit-image, and is skipped when they are not installed."""
import pytest
from sqlmodel import Session

from app.core.database import engine
from app.features.candidates.models import Candidate
from app.features.candidates.services.application_service import read_applications
from app.features.candidates.services.cv_storage_service import photo_file, save_photo_file
from app.features.identity.services import face_service
from app.features.identity.services.face_service import FaceProblem
from tests.test_candidates import approved_job, fake_drive  # noqa: F401  (a posted job and a fake Google Drive)
from tests.test_video_call import interview, livekit  # noqa: F401  (a scheduled interview and LiveKit settings)

# Made-up face vectors: the "camera picture" bytes say which vector the fake engine returns
# (the tests share one database, so every test uses faces of its own)
VECTORS = {b"same": [1.0, 0.0, 0.0], b"other": [0.0, 1.0, 0.0], b"mine": [0.0, 0.0, 1.0],
           b"unsure": [0.0, -0.9, 0.4]}                       # similarity 0.41 with "mine": possible, not certain


@pytest.fixture
def fake_faces(monkeypatch):
    def vector(data, allow_several=False):
        if data not in VECTORS:
            raise FaceProblem("no_face", "No face was found in the picture.")
        return VECTORS[data]
    monkeypatch.setattr(face_service, "face_vector", vector)
    monkeypatch.setattr(face_service, "engine_problem", lambda: "")


def give_photo(candidate_id: int, vector: list, email: str = "") -> None:
    with Session(engine) as session:
        candidate = session.get(Candidate, candidate_id)
        candidate.face_vector, candidate.face_status = vector, "ready"
        candidate.photo_path = save_photo_file(candidate, "photo.jpg", b"made-up photo bytes")
        if email:
            candidate.email = email
        session.add(candidate)
        session.commit()


def other_candidate(job_id: int, name: str, vector: list) -> int:
    with Session(engine) as session:
        other = Candidate(job_id=job_id, number=99, full_name=name, email="someone.else@example.com",
                          source="upload", source_key=f"test:{name}")
        session.add(other)
        session.commit()
        give_photo(other.id, vector)
        return other.id


def check(client, interview, picture: bytes) -> dict:  # noqa: F811
    answer = client.post(f"/api/sessions/{interview['id']}/identity/check", files={"frame": ("frame.jpg", picture)})
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_form_gives_the_photo_for_the_identity_check():
    headers = ["Timestamp", "Full name", "Email", "Upload your CV", "Upload a photo of your face"]
    rows = [headers,
            ["t1", "Rahim Uddin", "rahim@example.com", "https://drive.google.com/open?id=CV1",
             "https://drive.google.com/open?id=PHOTO1"],
            ["t2", "Nadia Rahman", "nadia@example.com", "https://drive.google.com/open?id=CV2", ""]]
    rahim, nadia = read_applications(rows)
    assert rahim.file_id == "CV1" and rahim.photo_id == "PHOTO1"                      # the photo is not taken for the CV
    assert nadia.file_id == "CV2" and nadia.photo_id == "" and nadia.has_photo_question
    old_form = read_applications([["Timestamp", "Name", "CV"], ["t1", "Rahim", "https://drive.google.com/open?id=CV1"]])
    assert old_form[0].has_photo_question is False and old_form[0].file_id == "CV1"     # a form without a photo works


def test_fetching_the_form_saves_the_photo_and_its_face(client, approved_job, fake_drive, fake_faces):  # noqa: F811
    """The whole Google Form import: the photo is saved with its face vector; an answer without a photo is marked."""
    from tests.test_candidates import fetch, link
    header = ("Timestamp", "Full Name", "Email", "Upload your CV", "Upload a photo of your face")
    cv_text = lambda name: f"{name}\nSkills: Python, FastAPI\nExperience: 4 years.".encode()  # noqa: E731
    fake_drive([["t1", "Rahim Uddin", "rahim@example.com", link("rahim.txt"), link("rahim.jpg")],
                ["t2", "Karim Hasan", "karim@example.com", link("karim.txt"), ""]],
               {"rahim.txt": cv_text("Rahim Uddin"), "karim.txt": cv_text("Karim Hasan"), "rahim.jpg": b"same"},
               header=header)
    assert fetch(client, approved_job)["added"] == 2
    with Session(engine) as db:
        rows = {c.full_name: c for c in db.query(Candidate).filter(Candidate.job_id == approved_job["id"])}
        rahim, karim = rows["Rahim Uddin"], rows["Karim Hasan"]
        assert rahim.face_status == "ready" and rahim.face_vector == VECTORS[b"same"]
        assert photo_file(rahim).read_bytes() == b"same"
        assert rahim.file_path.endswith(".txt")                                        # the CV stayed the CV
        assert karim.face_status == "no_photo" and not karim.photo_path


def test_photos_of_earlier_applications_are_added_once(client, approved_job, fake_drive, fake_faces):  # noqa: F811
    """A form that got its photo question ("Pictures") later: the next fetch adds the photos of saved answers."""
    from tests.test_candidates import fetch, link
    cv_text = b"Liam Gallagher\nSkills: Python\nExperience: 3 years."
    fake_drive([["t1", "Liam Gallagher", "liam@example.com", link("liam.txt")]], {"liam.txt": cv_text},
               header=("Timestamp", "Full Name", "Email", "Upload Your CV"))
    assert fetch(client, approved_job)["added"] == 1                                    # saved without a photo
    fake_drive([["t1", "Liam Gallagher", "liam@example.com", link("liam.txt"), link("liam.jpg")]],
               {"liam.txt": cv_text, "liam.jpg": b"same"},
               header=("Timestamp", "Full Name", "Email", "Upload Your CV", "Pictures"))
    again = fetch(client, approved_job)
    assert again["added"] == 0 and "1 photo(s) of earlier applications were added" in again["message"]
    liam = next(c for c in client.get(f"/api/jobs/{approved_job['id']}/candidates").json() if c["full_name"] == "Liam Gallagher")
    assert liam["has_photo"] is True
    assert client.get(f"/api/candidates/{liam['id']}/photo").content == b"same"
    assert "photo" not in fetch(client, approved_job)["message"]                       # done once, not at every fetch


def test_a_photo_can_be_uploaded_with_a_cv(client, approved_job, fake_faces):  # noqa: F811
    """Manual upload: the CV, the contact details and the photo of one person."""
    upload = lambda photo: client.post(  # noqa: E731
        f"/api/jobs/{approved_job['id']}/candidates/upload",
        files={"file": (f"cv-{photo[0]}.txt", f"Nadia Rahman {photo[0]}\nSkills: Python".encode()), "photo": photo},
        data={"full_name": "Nadia Rahman", "email": "nadia@example.com", "phone": "01700000009"}).json()
    added = upload(("nadia.jpg", b"same"))
    assert added["ok"] and added["message"].endswith("with the photo.")
    nadia = next(c for c in client.get(f"/api/jobs/{approved_job['id']}/candidates").json() if c["id"] == added["candidate_id"])
    assert nadia["has_photo"] is True and nadia["phone"] == "01700000009"
    assert client.get(f"/api/candidates/{nadia['id']}/photo").content == b"same"
    blurry = upload(("blurry.png", b"no face here"))
    assert blurry["ok"] and "no single clear face" in blurry["message"]                  # saved, but not usable
    wrong = upload(("photo.gif", b"same"))
    assert not wrong["ok"] and "JPG, PNG or WEBP" in wrong["message"]


def test_the_face_is_compared_and_a_person_decides(client, anonymous, interview, livekit, fake_faces):  # noqa: F811
    session, candidate = interview["id"], interview["candidate_id"]
    give_photo(candidate, VECTORS[b"mine"])
    assert client.get(f"/api/sessions/{session}/identity").json()["result"] == ""          # not checked yet
    early = client.post(f"/api/sessions/{session}/identity/check", files={"frame": ("f.jpg", b"mine")})
    assert early.status_code == 409                                                       # only during the call
    client.post(f"/api/sessions/{session}/start")

    same = check(client, interview, b"mine")
    assert same["result"] == "confident" and same["similarity"] == 1.0 and same["decision"] == ""
    assert check(client, interview, b"unsure")["result"] == "low"                         # 0.41: possible, not certain
    assert check(client, interview, b"nobody")["result"] == "no_face"

    other_candidate(interview["job_id"], "Morgan Davis", VECTORS[b"other"])
    other = check(client, interview, b"other")                                            # someone else's face
    assert other["result"] == "no_match" and other["better_match"]["name"] == "Morgan Davis"
    assert "Morgan Davis" in other["message"]

    confirmed = client.put(f"/api/sessions/{session}/identity/decision", json={"decision": "confirmed"}).json()
    assert confirmed["decision"] == "confirmed" and confirmed["decided_by"]
    back = client.put(f"/api/sessions/{session}/identity/decision", json={"decision": ""}).json()
    assert back["decision"] == "" and back["decided_by"] == ""
    assert client.put(f"/api/sessions/{session}/identity/decision", json={"decision": "maybe"}).status_code == 422

    runs = client.get(f"/api/sessions/{session}/identity").json()
    assert runs["photo_on_record"] is True and runs["same_person_at"] == face_service.SAME_PERSON


def test_without_a_photo_nothing_is_compared(client, anonymous, interview, livekit, fake_faces):  # noqa: F811
    session, candidate = interview["id"], interview["candidate_id"]
    client.post(f"/api/sessions/{session}/start")
    missing = check(client, interview, b"same")
    assert missing["result"] == "no_photo" and missing["similarity"] is None          # never a silent guess
    assert client.get(f"/api/candidates/{candidate}/photo").status_code == 404
    assert "photo_check" not in anonymous.get(f"/api/join/{interview['token']}").json()  # the candidate's page is unchanged


def test_access_privacy_and_deletion(client, anonymous, interview, livekit, fake_faces):  # noqa: F811
    session, candidate = interview["id"], interview["candidate_id"]
    give_photo(candidate, VECTORS[b"same"])
    for path in (f"/api/sessions/{session}/identity", f"/api/candidates/{candidate}/photo"):
        assert anonymous.get(path).status_code == 401                                     # interviewer only
    assert client.get("/api/sessions/999999/identity").status_code == 404
    assert client.get(f"/api/candidates/{candidate}/photo").content == b"made-up photo bytes"
    with Session(engine) as db:
        saved = photo_file(db.get(Candidate, candidate))
    assert saved and saved.is_file()
    assert client.delete(f"/api/candidates/{candidate}").status_code == 204
    assert not saved.exists()                                                             # deleted with the candidate


def test_the_real_face_models_tell_two_people_apart():
    skimage_data = pytest.importorskip("skimage.data")
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    if face_service.engine_problem():
        pytest.skip("the face models are not downloaded (python scripts/download_face_models.py)")
    # two public-domain photos that come with scikit-image (nothing is saved)
    astronaut = cv2.imencode(".jpg", cv2.cvtColor(skimage_data.astronaut(), cv2.COLOR_RGB2BGR))[1].tobytes()
    camera_man = cv2.imencode(".png", cv2.cvtColor(skimage_data.camera(), cv2.COLOR_GRAY2BGR))[1].tobytes()
    picture = cv2.imdecode(np.frombuffer(astronaut, np.uint8), cv2.IMREAD_COLOR)
    darker = cv2.imencode(".jpg", cv2.convertScaleAbs(picture, alpha=0.8, beta=-10))[1].tobytes()
    a, a_dark, b = (face_service.face_vector(x) for x in (astronaut, darker, camera_man))
    assert len(a) == 128
    assert face_service.similarity(a, a_dark) >= face_service.CONFIDENT                 # the same person, darker
    assert face_service.similarity(a, b) < face_service.SAME_PERSON                      # two different people
    with pytest.raises(FaceProblem) as nothing:
        face_service.face_vector(cv2.imencode(".png", np.full((200, 200, 3), 255, np.uint8))[1].tobytes())  # blank
    assert nothing.value.code == "no_face"
