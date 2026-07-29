"""
Write a simple text PDF, used to generate sample documents for the modules.

This is fixture tooling rather than lesson content. It lives here because
Modules 05 and 08 both need it and duplicating it would let the two copies
drift.

A PDF is a plain text container of numbered objects plus a cross reference
table of byte offsets, so a small one can be written directly with no PDF
library. Seeing that also makes it clearer why text extracted from a PDF so
often arrives without paragraph structure.
"""

from pathlib import Path


def _escape(text: str) -> str:
    """Backslash and both bracket types are special inside a PDF string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _page_stream(lines: list) -> bytes:
    """
    A PDF content stream: begin text, set font and leading, position the
    cursor, then emit each line followed by T* to move down one line.
    """
    parts = ["BT", "/F1 11 Tf", "14 TL", "72 720 Td"]
    for line in lines:
        parts.append(f"({_escape(line)}) Tj")
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def write_pdf(path: Path, pages: list) -> None:
    """
    Write pages to path. Each page is a list of text lines.

    Lines are not wrapped, so keep them under about 90 characters.
    """
    objects = []
    page_count = len(pages)

    # object numbering: 1 catalog, 2 pages, 3 font, then page and stream pairs
    page_ids = [4 + (i * 2) for i in range(page_count)]
    stream_ids = [5 + (i * 2) for i in range(page_count)]

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("latin-1")
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for index, page in enumerate(pages):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {stream_ids[index]} 0 R >>"
            ).encode("latin-1")
        )
        stream = _page_stream(page)
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    # assemble, recording the byte offset of every object for the xref table
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()

    path.write_bytes(bytes(out))
