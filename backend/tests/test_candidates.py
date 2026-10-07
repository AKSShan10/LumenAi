"""Candidates: fetching applications from the Google Form and manual upload. Every person must stay with their own CV."""
import random

import pytest
from sqlmodel import Session, select

from app.core.database import engine
from app.features.candidates.models import Candidate

from app.features.candidates.services import application_service
from app.features.candidates.services.application_service import SheetProblem, read_applications
from app.features.candidates.services.cv_storage_service import cv_file, storage_dir
from app.features.candidates.services.drive_service import file_id_from
from app.mcp_servers.client import McpError

SHEET = "https://docs.google.com/spreadsheets/d/made-up-sheet-id/edit"
HEADER = ("Timestamp", "Full Name", "Email", "Phone Number", "CV")


def link(file_name: str) -> str:
    return f"https://drive.google.com/open?id={file_name}"


@pytest.fixture
def approved_job(client, make_job) -> dict:
    """An approved job whose response sheet link is saved."""
    job = make_job(approve=True, title="Backend Developer", description="A made-up job used to test collecting CVs.")
    return client.put(f"/api/jobs/{job['id']}/response-sheet", json={"sheet_url": SHEET}).json()


@pytest.fixture
def fake_drive(tmp_path, monkeypatch):
    """A folder that plays Google Drive. write(rows, files) fills it. The Drive MCP server (a child
    process) reads the folder name from the environment when it starts."""
    monkeypatch.setenv("DRIVE_FAKE_FOLDER", str(tmp_path))

    def write(rows: list[list[str]], files: dict[str, bytes], header=HEADER):
        import csv
        with open(tmp_path / "responses.csv", "w", newline="", encoding="utf-8") as sheet:
            csv.writer(sheet).writerows([list(header)] + rows)
        for name, content in files.items():
            (tmp_path / name).write_bytes(content)
    return write


def check(client, job) -> dict:
    return client.get(f"/api/jobs/{job['id']}/applications/check").json()


def fetch(client, job) -> dict:
    return client.post(f"/api/jobs/{job['id']}/applications/fetch").json()


def saved_file(candidate_id: int) -> bytes:
    """The CV as it lies in the storage folder, found through the candidate's own row."""
    with Session(engine) as session:
        return cv_file(session.get(Candidate, candidate_id)).read_bytes()


def candidates(client, job) -> list[dict]:
    return client.get(f"/api/jobs/{job['id']}/candidates").json()


# ---------- reading the sheet (plain Python) ----------

def test_file_id_from_google_links():
    assert file_id_from("https://drive.google.com/open?id=1AbC_d-9") == "1AbC_d-9"
    assert file_id_from("https://drive.google.com/file/d/1AbC_d-9/view?usp=sharing") == "1AbC_d-9"
    assert file_id_from("https://docs.google.com/spreadsheets/d/SHEET123/edit#gid=0") == "SHEET123"
    assert file_id_from("1AbC_d-9") == "1AbC_d-9"
    assert file_id_from("not a link") == "" and file_id_from("https://example.com/cv.pdf") == ""


def test_columns_are_found_by_their_titles():
    rows = [["Timestamp", "Email Address", "Upload your CV (PDF)", "Your full name", "Phone"],
            ["10/6/2026 10:00:00", "a@example.com", link("a.pdf"), "Ayesha Khan", "000"]]
    application = read_applications(rows)[0]
    assert (application.name, application.email, application.file_id) == ("Ayesha Khan", "a@example.com", "a.pdf")
    assert application.phone == "000"
    yours = read_applications([list(HEADER), ["t1", "Rahim Uddin", "r@example.com", "01700000001", link("r.pdf")]])[0]
    assert (yours.name, yours.email, yours.phone, yours.file_id) == ("Rahim Uddin", "r@example.com", "01700000001", "r.pdf")

    with pytest.raises(SheetProblem) as problem:
        read_applications([["Timestamp", "Question 1", "Question 2"], ["x", "y", "z"]])
    assert "name" in str(problem.value) and "Question 1" in str(problem.value)       # says what to change
    with pytest.raises(SheetProblem):
        read_applications([])


def test_unusual_rows_get_a_warning():
    rows = [["Timestamp", "Full name", "Email", "CV"],                                # a sheet without a phone column works too
            ["t1", "No File", "nofile@example.com", ""],
            ["t2", "Two Files", "two@example.com", f"{link('one.pdf')}, {link('two.pdf')}"],
            ["t3", "Bad Email", "not-an-email", link("bad.pdf")],
            ["", "", "", ""]]                                                         # an empty row is skipped
    no_file, two_files, bad_email = read_applications(rows)
    assert no_file.file_id == "" and "No CV file" in no_file.warnings[0]
    assert two_files.file_id == "one.pdf" and "only the first" in two_files.warnings[0]
    assert "does not look right" in bad_email.warnings[0]


# ---------- checking and fetching (through the real Drive MCP server, reading a folder on this computer) ----------

def test_every_person_stays_with_their_own_cv(client, approved_job, fake_drive):
    """The file names say nothing about the owner, two people use the same file name pattern, and the rows
    are in a random order."""
    people = [(f"Person{n} Family{n}", f"person{n}@example.com", f"0170000000{n}", f"upload_{n * 7919 % 100}.txt")
              for n in range(1, 9)]
    files = {file: f"{name}\nMade-up CV. Secret marker of {email}.".encode() for name, email, phone, file in people}
    rows = [[f"10/6/2026 10:0{n}:00", name, email, phone, link(file)] for n, (name, email, phone, file) in enumerate(people)]
    random.Random(4).shuffle(rows)
    fake_drive(rows, files)

    result = fetch(client, approved_job)
    assert result["ok"] is True and result["added"] == 8 and result["needs_review"] == 0

    saved = candidates(client, approved_job)
    assert len(saved) == 8
    for row in saved:
        assert row["has_file"] is True and row["status"] == "new" and row["warnings"] == []
        text = saved_file(row["id"]).decode()
        assert text.startswith(row["full_name"])                                      # this person's CV ...
        assert f"Secret marker of {row['email']}." in text                           # ... and nobody else's
        assert row["phone"] == next(phone for name, email, phone, file in people if email == row["email"])
        # the file the page downloads is the same one
        assert client.get(f"/api/candidates/{row['id']}/cv").content == saved_file(row["id"])


def test_files_are_named_by_the_candidate_number(client, approved_job, fake_drive):
    """Two applicants upload a file with the same name. Neither overwrites the other."""
    fake_drive([["t1", "Rahim Uddin", "rahim@example.com", "1", link("a/CV.txt")],
                ["t2", "Karima Akter", "karima@example.com", "2", link("b_CV.txt")]],
               {"CV.txt": b"Rahim Uddin\nMade-up CV.", "b_CV.txt": b"Karima Akter\nMade-up CV."})
    fetch(client, approved_job)
    with Session(engine) as session:
        rows = session.exec(select(Candidate).where(Candidate.job_id == approved_job["id"])).all()
        for row in rows:
            if row.file_path:
                name = row.full_name.lower().replace(" ", "-")
                assert row.file_path == f"cvs/job_{row.job_id}/google_form/candidate_{row.id}_{name}.txt"
                assert (storage_dir() / row.file_path).is_file()


def test_the_check_counts_new_answers_and_downloads_nothing(client, approved_job, fake_drive):
    first = [["t1", "Rahim Uddin", "rahim@example.com", "1", link("r.txt")]]
    files = {"r.txt": b"Rahim Uddin\nMade-up CV.", "k.txt": b"Karima Akter\nMade-up CV."}
    fake_drive(first, files)
    answer = check(client, approved_job)
    assert (answer["ok"], answer["in_sheet"], answer["new"], answer["already_fetched"]) == (True, 1, 1, 0)
    assert candidates(client, approved_job) == []                                     # checking saves nothing

    assert fetch(client, approved_job)["added"] == 1
    answer = check(client, approved_job)
    assert (answer["new"], answer["already_fetched"]) == (0, 1) and "No new applications" in answer["message"]
    again = fetch(client, approved_job)
    assert again["added"] == 0 and "No new applications" in again["message"]          # nobody is added twice

    fake_drive(first + [["t2", "Karima Akter", "karima@example.com", "2", link("k.txt")]], files)
    assert check(client, approved_job)["new"] == 1                                    # the system knows about the new one
    assert fetch(client, approved_job)["added"] == 1
    assert sorted(c["full_name"] for c in candidates(client, approved_job)) == ["Karima Akter", "Rahim Uddin"]


def test_problems_are_flagged_for_a_person(client, approved_job, fake_drive):
    rows = [["t1", "Rahim Uddin", "rahim@example.com", "1", link("someone_else.txt")],     # another person's CV
            ["t2", "Karima Akter", "karima@example.com", "2", link("missing.txt")],        # the file is gone
            ["t3", "Tanvir Hasan", "tanvir@example.com", "3", link("scan.pdf")],           # cannot be read
            ["t4", "Nadia Islam", "nadia@example.com", "4", ""],                           # no file at all
            ["t5", "Rahim Uddin", "rahim@example.com", "1", link("rahim_again.txt")]]      # the same email again
    fake_drive(rows, {"someone_else.txt": b"Jamal Hossain\nMade-up CV of another person.",
                      "scan.pdf": b"this is not a real pdf", "rahim_again.txt": b"Rahim Uddin\nMade-up CV."})
    result = fetch(client, approved_job)
    assert result["added"] == 5 and result["needs_review"] == 3

    by_time = {c["applied_at"]: c for c in candidates(client, approved_job)}
    assert by_time["t1"]["status"] == "new" and "name from the form was not found" in by_time["t1"]["warnings"][0]
    assert by_time["t2"]["status"] == "needs_review" and "could not be downloaded" in by_time["t2"]["warnings"][0]
    assert by_time["t2"]["has_file"] is False
    assert by_time["t3"]["status"] == "needs_review" and "could not be read" in by_time["t3"]["warnings"][0]
    assert by_time["t3"]["has_file"] is True                                          # the file is kept all the same
    assert by_time["t4"]["status"] == "needs_review" and "No CV file" in by_time["t4"]["warnings"][0]
    assert by_time["t5"]["status"] == "new" and "more than once" in by_time["t5"]["warnings"][0]


def test_a_sheet_that_cannot_be_used_is_explained(client, approved_job, fake_drive, monkeypatch):
    fake_drive([["x", "y", "z"]], {}, header=("Timestamp", "Question 1", "Question 2"))
    for result in (check(client, approved_job), fetch(client, approved_job)):
        assert result["ok"] is False and "name" in result["message"]
    assert candidates(client, approved_job) == []

    def broken(server, tool, arguments=None):
        raise McpError("TimeoutError while calling the MCP server")
    monkeypatch.setattr(application_service, "call_tool", broken)
    result = fetch(client, approved_job)
    assert result["ok"] is False and "did not answer" in result["message"]


def test_only_a_few_cvs_are_downloaded_per_click(client, approved_job, fake_drive, monkeypatch):
    monkeypatch.setattr(application_service, "MAX_PER_CLICK", 2)
    rows = [[f"t{n}", f"Person{n} Family{n}", f"p{n}@example.com", str(n), link(f"{n}.txt")] for n in range(1, 6)]
    fake_drive(rows, {f"{n}.txt": f"Person{n} Family{n}\nMade-up CV.".encode() for n in range(1, 6)})
    first = fetch(client, approved_job)
    assert first["added"] == 2 and first["left_for_next_time"] == 3 and "click Fetch new applications again" in first["message"]
    assert fetch(client, approved_job)["added"] == 2 and fetch(client, approved_job)["added"] == 1
    assert len(candidates(client, approved_job)) == 5


def test_the_sample_folder_works(client, approved_job):
    """tests/fake_drive holds three made-up applications for demos without a Google account."""
    assert check(client, approved_job)["new"] == 3
    assert fetch(client, approved_job)["added"] == 3
    names = {c["full_name"]: c for c in candidates(client, approved_job)}
    assert set(names) == {"Rahim Uddin", "Karima Akter", "Tanvir Hasan"}
    assert all(c["status"] == "new" and c["warnings"] == [] and c["phone"] for c in names.values())


def test_same_name_and_same_file_name_still_give_two_files(client, approved_job, fake_drive):
    """Two different people with the same name, each sending a file called CV: nothing overlaps."""
    fake_drive([["t1", "Rahim Uddin", "rahim.one@example.com", "1", link("one_CV.txt")],
                ["t2", "Rahim Uddin", "rahim.two@example.com", "2", link("two_CV.txt")]],
               {"one_CV.txt": b"Rahim Uddin\nMade-up CV of the first one.", "two_CV.txt": b"Rahim Uddin\nMade-up CV of the second one."})
    assert fetch(client, approved_job)["added"] == 2
    upload_answer = client.post(f"/api/jobs/{approved_job['id']}/candidates/upload", data={"full_name": "Rahim Uddin"},
                                files={"file": ("CV.txt", b"Rahim Uddin\nMade-up CV of a third one, uploaded by hand.")}).json()
    assert upload_answer["ok"] is True
    rows = candidates(client, approved_job)
    with Session(engine) as session:
        paths = [session.get(Candidate, row["id"]).file_path for row in rows]
    assert len(set(paths)) == 3                                                       # three files, three places
    by_email = {row["email"]: saved_file(row["id"]).decode() for row in rows}
    assert "first one" in by_email["rahim.one@example.com"] and "second one" in by_email["rahim.two@example.com"]
    assert "uploaded by hand" in by_email[""]
    assert sorted(path.split("/")[2] for path in paths) == ["google_form", "google_form", "uploaded"]


def test_a_name_in_another_alphabet_still_gets_a_file(client, approved_job):
    answer = client.post(f"/api/jobs/{approved_job['id']}/candidates/upload", data={"full_name": "রহিম উদ্দিন"},
                         files={"file": ("cv.txt", b"A made-up CV with a name in Bangla letters.")}).json()
    with Session(engine) as session:
        row = session.get(Candidate, answer["candidate_id"])
        assert row.file_path == f"cvs/job_{row.job_id}/uploaded/candidate_{row.id}.txt" and cv_file(row).is_file()


# ---------- manual upload ----------

def upload(client, job, name, data, **fields):
    return client.post(f"/api/jobs/{job['id']}/candidates/upload", files={"file": (name, data)}, data=fields).json()


def test_manual_upload_saves_the_file_and_the_person(client, approved_job):
    answer = upload(client, approved_job, "internal referral.txt", b"Nadia Islam\nMade-up CV from a colleague.",
                    full_name="Nadia Islam", email="nadia@example.com", phone="01700000009")
    assert answer["ok"] is True
    row = candidates(client, approved_job)[0]
    assert (row["full_name"], row["email"], row["phone"], row["source"]) == ("Nadia Islam", "nadia@example.com", "01700000009", "upload")
    assert row["original_file_name"] == "internal referral.txt" and row["has_file"] is True and row["status"] == "new"
    assert saved_file(row["id"]) == b"Nadia Islam\nMade-up CV from a colleague."
    with Session(engine) as session:                                                  # uploads have their own folder
        assert session.get(Candidate, row["id"]).file_path == f"cvs/job_{approved_job['id']}/uploaded/candidate_{row['id']}_nadia-islam.txt"

    # the same file again is skipped; a file without a name is kept and flagged
    assert upload(client, approved_job, "copy.txt", b"Nadia Islam\nMade-up CV from a colleague.")["ok"] is False
    assert upload(client, approved_job, "unknown.txt", b"A made-up CV with no name typed.")["ok"] is True
    assert "No name was given" in candidates(client, approved_job)[0]["warnings"][0]
    assert len(candidates(client, approved_job)) == 2


def test_bad_uploads_are_refused(client, approved_job):
    assert "only PDF, DOCX and TXT" in upload(client, approved_job, "photo.png", b"x")["message"]
    assert "larger than 5 MB" in upload(client, approved_job, "big.txt", b"a" * (5 * 1024 * 1024 + 1))["message"]
    assert candidates(client, approved_job) == []
    scan = upload(client, approved_job, "scan.pdf", b"this is not a real pdf")       # kept, for a person to look at
    assert scan["ok"] is True and candidates(client, approved_job)[0]["status"] == "needs_review"


# ---------- rules ----------

def test_deleting_a_candidate_removes_the_file(client, approved_job):
    fetch(client, approved_job)
    row = candidates(client, approved_job)[0]
    assert "cv_text" not in row                                                       # the list does not carry the CVs
    with Session(engine) as session:
        path = cv_file(session.get(Candidate, row["id"]))
    assert path.is_file()
    assert client.delete(f"/api/candidates/{row['id']}").status_code == 204
    assert not path.exists()
    assert client.get(f"/api/candidates/{row['id']}/cv").status_code == 404
    assert len(candidates(client, approved_job)) == 2


def test_rules(client, anonymous, make_job):
    draft = make_job(title="Draft Tester")
    assert client.post(f"/api/jobs/{draft['id']}/applications/fetch").status_code == 400      # not approved
    assert client.get(f"/api/jobs/{draft['id']}/applications/check").status_code == 400
    assert client.post(f"/api/jobs/{draft['id']}/candidates/upload", files={"file": ("a.txt", b"x")}).status_code == 400
    assert client.put(f"/api/jobs/{draft['id']}/response-sheet", json={"sheet_url": "not a link"}).status_code == 422
    approved = make_job(approve=True, title="No Sheet Tester", description="A made-up job without a sheet link.")
    assert "Save the link" in client.get(f"/api/jobs/{approved['id']}/applications/check").json()["message"]
    assert client.post("/api/jobs/999999/applications/fetch").status_code == 404
    assert client.get("/api/jobs/999999/candidates").status_code == 404
    for call in (anonymous.post("/api/jobs/1/applications/fetch"), anonymous.get("/api/jobs/1/applications/check"),
                 anonymous.get("/api/jobs/1/candidates"), anonymous.get("/api/candidates/1/cv"),
                 anonymous.delete("/api/candidates/1"), anonymous.get("/api/drive-check"),
                 anonymous.put("/api/jobs/1/response-sheet", json={"sheet_url": SHEET})):
        assert call.status_code == 401


def test_settings_check(client):
    answer = client.get("/api/drive-check").json()
    assert answer["ok"] is True and "Fake Google Drive" in answer["message"]


# ---------- the Google path, with a pretend Google answering ----------

class PretendGoogle:
    """Answers like the Google Drive API for one sheet and two files."""
    def __init__(self):
        self.asked = []

    def get(self, url, params=None, timeout=None):
        self.asked.append((url.split("/drive/v3")[1], dict(params or {})))
        path = self.asked[-1][0]

        class Answer:
            status_code, content = 200, b""
            _json = {}

            def json(self):
                return self._json
        answer = Answer()
        if path == "/files/SHEET1":
            answer._json = {"mimeType": "application/vnd.google-apps.spreadsheet"}
        elif path == "/files/SHEET1/export":
            answer.content = ("\ufeffTimestamp,Full Name,Email,Phone Number,CV\r\n"
                              "t1,\"Uddin, Rahim\",rahim@example.com,01700000001,https://drive.google.com/open?id=FILE1\r\n").encode()
        elif path == "/files/FILE1":
            answer._json = {"name": "Rahim CV.pdf", "mimeType": "application/pdf"}
            answer.content = b"%PDF-made-up"
        elif path == "/files/DOC1":
            answer._json = {"name": "Karima CV", "mimeType": "application/vnd.google-apps.document"}
        elif path == "/files/DOC1/export":
            answer.content = b"%PDF-exported"
        elif path == "/files/NOT_A_SHEET":
            answer._json = {"mimeType": "application/pdf"}
        else:
            answer.status_code = 404
        return answer


def test_google_answers_are_read_correctly(monkeypatch):
    from app.core import config
    from app.features.candidates.services import drive_service
    google = PretendGoogle()
    monkeypatch.setattr(config, "DRIVE_PROVIDER", "google")
    monkeypatch.setattr(drive_service, "_session", lambda: google)

    rows = drive_service.read_response_sheet("https://docs.google.com/spreadsheets/d/SHEET1/edit#gid=0")
    assert rows == [["Timestamp", "Full Name", "Email", "Phone Number", "CV"],
                    ["t1", "Uddin, Rahim", "rahim@example.com", "01700000001", "https://drive.google.com/open?id=FILE1"]]
    assert read_applications(rows)[0].file_id == "FILE1"

    assert drive_service.download_file("FILE1") == ("Rahim CV.pdf", b"%PDF-made-up")
    assert drive_service.download_file("DOC1") == ("Karima CV.pdf", b"%PDF-exported")      # a Google Doc becomes a PDF
    assert ("/files/DOC1/export", {"mimeType": "application/pdf"}) in google.asked

    with pytest.raises(drive_service.DriveError) as problem:
        drive_service.read_response_sheet("https://drive.google.com/file/d/NOT_A_SHEET/view")
    assert "does not open a Google Sheet" in str(problem.value)
    with pytest.raises(drive_service.DriveError) as problem:
        drive_service.download_file("GONE")
    assert "Share the job's folder" in str(problem.value)


def test_a_missing_key_file_is_explained(monkeypatch):
    from app.core import config
    from app.features.candidates.services import drive_service
    monkeypatch.setattr(config, "DRIVE_PROVIDER", "google")
    monkeypatch.setattr(config, "GOOGLE_DRIVE_KEY_FILE", "secrets/no-such-key.json")
    answer = drive_service.check_drive()
    assert answer["ok"] is False and "key file was not found" in answer["message"]
