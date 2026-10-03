"""Os leitores do Agno que `collections add -f` usa dependem de pacotes
opcionais (pypdf, python-docx...). Sem eles a ingestão só falha em produção,
no upload — este teste garante que estão nas dependências do projeto."""

import io

import pytest


@pytest.mark.parametrize(
    "modulo",
    [
        "agno.knowledge.reader.pdf_reader",
        "agno.knowledge.reader.docx_reader",
        "agno.knowledge.reader.csv_reader",
        "agno.knowledge.reader.pptx_reader",
    ],
)
def test_leitor_importa(modulo):
    __import__(modulo)


def test_planilhas_tem_backend():
    import openpyxl  # noqa: F401  (.xlsx)
    import xlrd  # noqa: F401  (.xls)


def test_docx_extrai_texto():
    from docx import Document

    from agno.knowledge.reader.docx_reader import DocxReader

    doc = Document()
    doc.add_paragraph("Prazo de garantia: 12 meses")
    arquivo = io.BytesIO()
    doc.save(arquivo)
    arquivo.seek(0)
    arquivo.name = "manual.docx"

    textos = [d.content for d in DocxReader().read(arquivo)]
    assert any("12 meses" in t for t in textos)
