from datetime import date

import pytest
from pydantic import BaseModel

from contextos.ingest.classify import (
    SubjectRef,
    classify,
    classify_rules,
    clean_title,
    normalise_semester,
)
from contextos.ingest.extract import Extracted
from contextos.llm import LLMError, LLMProvider
from contextos.models import DocType

TODAY = date(2026, 10, 15)
SUBJECTS = [
    SubjectRef(1, "Database Management Systems", "BCS403", ("DBMS",), "Sem 4"),
    SubjectRef(2, "Operating Systems", "BCS303", ("OS",), "Sem 3"),
    SubjectRef(3, "Computer Networks", None, ("CN",)),
]


def rules(filename: str, text: str = "", subjects=SUBJECTS):
    return classify_rules(filename, Extracted(text, "pdf"), subjects, today=TODAY)


@pytest.mark.parametrize("filename, text, doc_type", [
    ("DBMS_Assignment_2.pdf", "", DocType.assignment),
    ("os question paper 2024.pdf", "", DocType.question_paper),
    ("scan0001.pdf", "USN\nMax. Marks: 100\nAnswer any FIVE questions", DocType.question_paper),
    ("CN Lab Manual.pdf", "", DocType.lab),
    ("BCS403 syllabus.pdf", "Course outcomes\nTeaching hours", DocType.syllabus),
    ("Notice_exam_fee.pdf", "All students are hereby informed", DocType.notice),
    ("Module3_final(2).pdf", "Module 3: Transactions and concurrency", DocType.notes),
])
def test_doc_types(filename, text, doc_type):
    assert rules(filename, text).doc_type == doc_type


def test_pptx_is_slides():
    r = classify_rules("Week 4.pptx", Extracted("Normalisation", "pptx"), SUBJECTS, today=TODAY)
    assert r.doc_type == DocType.slides


def test_subject_from_alias_in_filename():
    r = rules("dbms_notes_module1.pdf")
    assert r.subject == "Database Management Systems"
    assert r.semester == "Sem 4"  # inherited from the subject
    assert r.confidence >= 0.6


def test_subject_from_course_code_in_text():
    assert rules("unit1.pdf", "BCS303 - Process scheduling notes").subject == "Operating Systems"


def test_short_alias_needs_caps_in_body_text():
    # "os" inside ordinary lowercase prose must not mean Operating Systems.
    assert rules("lecture.pdf", "the cos and sin of os angles").subject is None
    assert rules("lecture.pdf", "OS process scheduling").subject == "Operating Systems"


def test_semester_in_filename_beats_subject_default():
    assert rules("DBMS 5th sem notes.pdf").semester == "Sem 5"


@pytest.mark.parametrize("raw, expected", [
    ("5", "Sem 5"), ("V", "Sem 5"), ("fifth", "Sem 5"), ("5th sem", "Sem 5"),
    ("Semester 5", "Sem 5"), ("Sem 5", "Sem 5"), ("nonsense", None), ("", None), (None, None),
])
def test_normalise_semester(raw, expected):
    assert normalise_semester(raw) == expected


@pytest.mark.parametrize("filename, meta, text, expected", [
    ("Module3_final(2).pdf", None, "", "Module 3"),
    ("Module3_final(2) (1).pdf", None, "", "Module 3"),
    ("dbms_assignment_2.pdf", None, "", "DBMS Assignment 2"),
    ("BCS403-notes-v2.pdf", None, "", "BCS403 Notes"),
    ("IMG_20261012.pdf", "Microsoft Word - OS Lab Record.docx", "", "OS Lab Record"),
    ("scan0001.pdf", None, "VTU\nOperating Systems Question Paper 2024\n...", "Operating Systems Question Paper 2024"),  # noqa: E501
])
def test_clean_title(filename, meta, text, expected):
    assert clean_title(filename, meta, text, known_terms=["DBMS", "BCS403"]) == expected


def test_title_from_text_skips_the_letterhead():
    text = ("RV College of Engineering\nDepartment of CSE\n"
            "Course: Design and Analysis of Algorithms (BCS401)\nAssignment - II\n"
            "Submit by 4th November 2026")
    daa = [SubjectRef(1, "Design and Analysis of Algorithms", "BCS401", ("DAA",))]
    r = rules("IMG_20261012_0001.pdf", text, subjects=daa)
    assert r.title == "DAA Assignment II"
    assert r.subject == "Design and Analysis of Algorithms"
    assert [(d.title, d.due) for d in r.deadlines] == [("DAA Assignment II", date(2026, 11, 4))]


@pytest.mark.parametrize("filename", [
    "IMG_20261014_scan.pdf", "CamScanner 10-14-2026 10.30.pdf", "scan0003.pdf",
    "WhatsApp Image 2026-10-12 at 10.30.15.jpeg", "Document (3).pdf", "IMG20261014.pdf",
])
def test_camera_and_scanner_names_are_junk(filename):
    text = "Operating Systems (BCS303)\nLab Record - Experiment 4\n"
    assert clean_title(filename, None, text, ["OS", "BCS303"], "OS") == \
        "OS Lab Record Experiment 4"


@pytest.mark.parametrize("filename", ["Documentation.pdf", "Image Processing Notes.pdf",
                                      "Newton Laws.pdf"])
def test_real_names_that_start_like_junk_are_kept(filename):
    assert clean_title(filename, None, "") == filename.removesuffix(".pdf")


def test_assignment_deadline_found():
    r = rules("DBMS_Assignment_2.pdf", "Last date of submission: 28/10/2026")
    assert [(d.title, d.due) for d in r.deadlines] == [("DBMS Assignment 2", date(2026, 10, 28))]


# -- LLM fallback -----------------------------------------------------------------


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, reply: dict | Exception):
        super().__init__("fake-model")
        self.reply = reply
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema: type[BaseModel], *, system: str = ""):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return schema.model_validate(self.reply)


def test_confident_rules_skip_the_llm():
    llm = FakeLLM({})
    result = classify("DBMS_Assignment_2.pdf", Extracted("", "pdf"), SUBJECTS, llm=llm,
                      today=TODAY)
    assert llm.prompts == []
    assert result.classified_by == "rules"


def test_unclear_file_asks_the_llm_with_a_snippet_only():
    llm = FakeLLM({
        "doc_type": "assignment", "subject": "dbms", "title": "Transactions Assignment",
        "semester": "fourth", "deadlines": [{"title": "Submit", "due_date": "2026-11-02"}],
    })
    text = "x" * 5000
    result = classify("scan0001.pdf", Extracted(text, "pdf"), SUBJECTS, llm=llm, today=TODAY,
                      snippet_chars=1500)
    assert result.classified_by == "fake"
    assert result.subject == "Database Management Systems"  # alias resolved to the real name
    assert result.semester == "Sem 4"
    assert result.deadlines[0].due == date(2026, 11, 2)
    assert "x" * 1500 in llm.prompts[0] and "x" * 1501 not in llm.prompts[0]


def test_llm_failure_falls_back_to_rules():
    llm = FakeLLM(LLMError("quota exceeded"))
    result = classify("scan0001.pdf", Extracted("unclear text", "pdf"), SUBJECTS, llm=llm,
                      today=TODAY)
    assert result.classified_by == "rules"
    assert "quota" in result.llm_error


def test_no_text_and_junk_name_skips_the_llm():
    llm = FakeLLM({"doc_type": "notes", "title": "x"})
    result = classify("scan0003.pdf", Extracted("", "ocr_unavailable"), SUBJECTS, llm=llm,
                      today=TODAY)
    assert llm.prompts == [] and result.confidence < 0.6


def test_filename_only_ai_guess_is_not_sure():
    llm = FakeLLM({"doc_type": "notes", "subject": "Physics", "title": "Optics"})
    result = classify("optics_week2.pdf", Extracted("", "ocr_unavailable"), SUBJECTS, llm=llm,
                      today=TODAY)
    assert len(llm.prompts) == 1 and result.confidence < 0.6


def test_unexpected_ai_reply_still_falls_back_to_rules():
    llm = FakeLLM({"steps": ["not a classification"]})  # fails schema validation
    result = classify("scan0001.pdf", Extracted("unclear text", "pdf"), SUBJECTS, llm=llm,
                      today=TODAY)
    assert result.classified_by == "rules" and result.llm_error.startswith("AI error")


def test_llm_may_propose_a_new_subject():
    llm = FakeLLM({"doc_type": "notes", "subject": "Machine Learning", "title": "Intro"})
    result = classify("scan.pdf", Extracted("Gradient descent", "pdf"), SUBJECTS, llm=llm,
                      today=TODAY)
    assert result.subject == "Machine Learning"
