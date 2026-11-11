"""Contest: physical page invariants even when OCR is needed."""
import io

from pypdf import PdfWriter

from powercontext.builtin.sources.pdf_pages import parse_pdf_pages, pdf_page_source_id, rank_pdf_pages, PdfPageSource
from powercontext.sources.models import SourceMaterialization


def test_all_physical_pages_survive_and_references_stable():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    pages = parse_pdf_pages('annual-2026', buffer.getvalue())
    assert len(pages) == 2
    assert [p.page_number for p in pages] == [1, 2]
    assert all(p.requires_ocr for p in pages)
    assert pdf_page_source_id('annual-2026', 1) != pdf_page_source_id('annual-2026', 2)


def test_retrieval_selects_evidence_page_not_unrelated():
    def page(n, text):
        return PdfPageSource(name=pdf_page_source_id('report', n), materialization=SourceMaterialization.CAPTURED,
                             document_id='report', pdf_digest='x', page_number=n, total_pages=3, text=text)
    result = rank_pdf_pages('2026 operating revenue', (page(1, 'Company introduction'),
                           page(2, '2026 operating revenue was 5000 million'), page(3, 'Assets balance')))
    assert result[0].page_number == 2
