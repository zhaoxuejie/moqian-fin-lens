import json
from pathlib import Path

import pytest

from core.errors import AppError, ErrorCode
from parse import PdfDoc, is_statement_page, locate_statements

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
GOLD_DIR = EVAL_DIR / "gold"
PDF_DIR = EVAL_DIR / "pdf"

KINDS = ("income", "balance", "cashflow")
TOLERANCE = 2
FILLER = "项目2024年度2023年度" * 8


def _gold_files() -> list[Path]:
    return sorted(GOLD_DIR.glob("*.json"))


def _write_contract_pdf(path: Path) -> None:
    """构造一份极小的非财报 PDF（合同片段），用于验证错误码分支。"""
    content = b"BT /F1 12 Tf 72 720 Td (Contract sample, not a financial report) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    chunks: list[bytes] = [b"%PDF-1.4\n"]
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(b"%d 0 obj\n" % index + body + b"\nendobj\n")

    xref_offset = sum(len(chunk) for chunk in chunks)
    xref = b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    xref += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    trailer = b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_offset,
    )
    path.write_bytes(b"".join(chunks) + xref + trailer)


@pytest.mark.skipif(not _gold_files(), reason="评估集金标不存在")
def test_locate_matches_gold_within_tolerance():
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    for gold_file in _gold_files():
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        pdf = pdf_index.get(gold_file.stem)
        if pdf is None:
            pytest.skip(f"缺少评估集 PDF：{gold_file.stem}")

        with PdfDoc(pdf) as doc:
            pages = [doc.page_text(i) for i in range(1, doc.page_count + 1)]
        located = locate_statements(pages)

        for kind in KINDS:
            expected = gold["statements"][kind]["start"]
            assert expected is not None, f"{gold_file.stem} 金标缺失 {kind}"
            actual = getattr(located, kind).start
            assert abs(actual - expected) <= TOLERANCE, (
                f"{gold_file.stem} {kind}：实际 {actual}，金标 {expected}"
            )


@pytest.mark.parametrize(
    ("heading", "kind", "expected"),
    [
        ("合并利润表", "income", True),
        ("合并 利润表", "income", True),
        ("合并\n利润表", "income", True),
        ("合并利润表（续）", "income", True),
        ("合并利润及利润分配表", "income", True),
        ("合并资产负债表", "balance", True),
        ("合并资产负债表（续）", "balance", True),
        ("合并现金流量表", "cashflow", True),
        ("母公司利润表", "income", False),
        ("母公司资产负债表", "balance", False),
    ],
)
def test_heading_typography_variants(heading: str, kind: str, expected: bool):
    accounts = {
        "income": "营业收入 1,234,567.89 营业成本 1,000,000.00",
        "balance": "流动资产 5,000,000.00 资产总计 10,000,000.00 负债合计 4,000,000.00",
        "cashflow": "经营活动产生的现金流量：销售商品收到的现金 1,000,000.00",
    }[kind]
    page = f"{heading} 单位：元 {FILLER} {accounts}"
    assert is_statement_page(page, kind) is expected


def test_non_report_pdf_raises_locate_failed(tmp_path):
    pdf_path = tmp_path / "contract.pdf"
    _write_contract_pdf(pdf_path)

    with PdfDoc(pdf_path) as doc:
        pages = [doc.page_text(i) for i in range(1, doc.page_count + 1)]

    with pytest.raises(AppError) as exc_info:
        locate_statements(pages)

    assert exc_info.value.code == ErrorCode.STATEMENT_LOCATE_FAILED
    assert exc_info.value.detail["missing"] == ["income", "balance", "cashflow"]


def test_pdfdoc_page_bounds_and_bookmarks(tmp_path):
    pdf_path = tmp_path / "contract.pdf"
    _write_contract_pdf(pdf_path)

    with PdfDoc(pdf_path) as doc:
        assert doc.page_count == 1
        assert "Contract sample" in doc.page_text(1)
        with pytest.raises(IndexError):
            doc.page_text(0)
        with pytest.raises(IndexError):
            doc.page_text(2)
        assert doc.bookmarks() == []


@pytest.mark.skipif(not _gold_files(), reason="评估集金标不存在")
def test_bookmarks_are_readable_on_real_report():
    pdf_index = {path.stem: path for path in PDF_DIR.rglob("*.pdf")}
    pdf = pdf_index.get("688111_金山办公_2024年年度报告")
    if pdf is None:
        pytest.skip("缺少带书签的评估集 PDF")

    with PdfDoc(pdf) as doc:
        bookmarks = doc.bookmarks()

    assert any("合并资产负债表" in title for title, _ in bookmarks)
    assert all(page >= 1 for _, page in bookmarks)
