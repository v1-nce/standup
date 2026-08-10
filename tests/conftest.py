"""Fixtures shared by every test that needs a real project on disk."""

import base64
import subprocess
from io import BytesIO

import pytest
from docx import Document
from openpyxl import Workbook
from pptx import Presentation

from standup.core import pipeline
from standup.core.projects import ProjectStore


@pytest.fixture
def repo(tmp_path):
    """A small git repository: a hub, a leaf, a doc that mentions the hub, and one commit."""
    path = tmp_path / "repo"
    (path / "src").mkdir(parents=True)
    (path / "src" / "hub.py").write_text("class Router:\n    pass\n")
    (path / "src" / "leaf.py").write_text("def alone():\n    pass\n")
    (path / "README.md").write_text("The Router matters here.\n")
    for command in (
        ["init", "-q"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "Tester"],
        ["add", "-A"],
        ["commit", "-qm", "first commit"],
    ):
        subprocess.run(["git", "-C", str(path), *command], check=True, capture_output=True)
    return path


def pdf_saying(words: str) -> bytes:
    """The smallest PDF that really carries text, so extraction is tested against a real file."""
    stream = f"BT /F1 12 Tf 20 100 Td ({words}) Tj ET".encode()
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        (
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
            b"/Resources<</Font<</F1 5 0 R>>>>>>"
        ),
        b"<</Length %d>>stream\n%s\nendstream" % (len(stream), stream),
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj" % number + body + b"endobj\n"

    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, start)
    return bytes(out)


def xlsx_saying(words: str) -> bytes:
    book = Workbook()
    book.active.append([words])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def pptx_saying(words: str) -> bytes:
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    box = slide.shapes.add_textbox(0, 0, 1000, 1000)
    box.text_frame.text = words
    buffer = BytesIO()
    deck.save(buffer)
    return buffer.getvalue()


def docx_saying(words: str) -> bytes:
    document = Document()
    document.add_paragraph(words)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# The smallest possible PNG: a single red pixel, valid enough for any real decoder.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(store, repo):
    """A project with the repo attached — every path it derives is prefixed by the resource id."""
    made = store.create("Demo")
    store.attach(made.id, str(repo))
    return store.get(made.id)


@pytest.fixture
def resource_id(project):
    return project.resources[0].id


@pytest.fixture
async def index(store, project):
    return await pipeline.indexed(store, project.id)
