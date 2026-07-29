"""
Generate the sample documents used by chunk_viewer.py.

Creates the same text as a .txt, a .docx and a .pdf, so the same content can be
loaded three different ways and the differences between loaders are visible.

The PDF is written directly rather than with a PDF library, by common/sample_pdf.py.
Module 08 needs the same helper, which is why it lives there rather than here.

Usage:
    python make_samples.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.sample_pdf import write_pdf

HERE = Path(__file__).resolve().parent

PAGES = [
    [
        "Chunking and why it matters",
        "",
        "A language model can only read so much text at once. Any document",
        "longer than that has to be broken into pieces before it can be",
        "embedded, searched or passed as context.",
        "",
        "The size of those pieces is a trade off. Large chunks keep more",
        "surrounding context together, which helps the model understand what it",
        "is reading, but they dilute search: a chunk about six different topics",
        "matches weakly against a question about any one of them.",
        "",
        "Small chunks retrieve precisely, because each one is about a single",
        "thing. The risk is that a sentence loses the paragraph that explained",
        "it, and the model is handed a fact with no context.",
    ],
    [
        "Overlap",
        "",
        "Overlap repeats the end of one chunk at the start of the next. It",
        "exists because a naive split can land in the middle of a sentence, or",
        "separate a claim from the evidence supporting it.",
        "",
        "A common starting point is an overlap of about ten to twenty percent",
        "of the chunk size. Too little and boundaries stay sharp; too much and",
        "the same text is stored and searched several times over, which costs",
        "storage and can return near duplicate results.",
        "",
        "Separators matter as much as size. Splitting on paragraph breaks",
        "first, then line breaks, then spaces, keeps related sentences together",
        "far more often than cutting blindly at a character count.",
    ],
]


def write_txt(path: Path) -> None:
    lines = []
    for page in PAGES:
        lines.extend(page)
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_docx(path: Path) -> None:
    from docx import Document

    document = Document()
    for index, page in enumerate(PAGES):
        for line in page:
            if line:
                document.add_paragraph(line)
        if index < len(PAGES) - 1:
            document.add_page_break()
    document.save(path)


def main() -> int:
    write_txt(HERE / "sample.txt")
    write_docx(HERE / "sample.docx")
    write_pdf(HERE / "sample.pdf", PAGES)

    for name in ("sample.txt", "sample.docx", "sample.pdf"):
        size = (HERE / name).stat().st_size
        print(f"wrote {name} ({size} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
