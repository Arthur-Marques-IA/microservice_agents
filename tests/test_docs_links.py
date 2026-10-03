"""Os links relativos da documentação não podem apontar para o nada.

README, AGENTS, ROADMAP e `docs/*.md` se referenciam entre si (e a imagens). Mover
ou renomear um arquivo, ou um título, sem atualizar quem aponta para ele passava
despercebido; aqui quebra o CI.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DOCUMENTOS = sorted({RAIZ / "README.md", RAIZ / "AGENTS.md", RAIZ / "ROADMAP.md", *(RAIZ / "docs").glob("*.md")})

_BLOCO_DE_CODIGO = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
_CODIGO_EM_LINHA = re.compile(r"`[^`\n]*`")
_LINK_MARKDOWN = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)")
_LINK_HTML = re.compile(r"""(?:src|srcset|href)=["']([^"']+)["']""")
_TITULO = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)


def _sem_codigo(texto: str) -> str:
    return _CODIGO_EM_LINHA.sub("", _BLOCO_DE_CODIGO.sub("", texto))


def _slug(titulo: str) -> str:
    """O âncora que o GitHub gera para um título."""
    titulo = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", titulo).replace("`", "")
    titulo = re.sub(r"[^\w\s-]", "", titulo.lower())
    return re.sub(r"\s", "-", titulo.strip())


def _ancoras(arquivo: Path) -> set[str]:
    texto = _BLOCO_DE_CODIGO.sub("", arquivo.read_text(encoding="utf-8"))
    vistos: dict[str, int] = {}
    ancoras = set()
    for titulo in _TITULO.findall(texto):
        base = _slug(titulo)
        n = vistos.get(base, 0)
        vistos[base] = n + 1
        ancoras.add(base if n == 0 else f"{base}-{n}")
    return ancoras


def _alvos(arquivo: Path) -> list[str]:
    texto = _sem_codigo(arquivo.read_text(encoding="utf-8"))
    return _LINK_MARKDOWN.findall(texto) + _LINK_HTML.findall(texto)


def _nome(caminho: Path) -> Path:
    return caminho.relative_to(RAIZ) if caminho.is_relative_to(RAIZ) else caminho


def _confere(arquivo: Path, alvo: str) -> str | None:
    if re.match(r"^[a-z][a-z0-9+.-]*:", alvo, re.I):  # http:, https:, mailto:...
        return None
    caminho, _, ancora = alvo.partition("#")
    destino = (arquivo.parent / caminho).resolve() if caminho else arquivo
    if not destino.exists():
        return f"{alvo}: {_nome(destino)} não existe"
    if ancora and destino.suffix == ".md" and ancora.lower() not in _ancoras(destino):
        return f"{alvo}: não há título com essa âncora em {_nome(destino)}"
    return None


@pytest.mark.parametrize("arquivo", DOCUMENTOS, ids=lambda p: str(p.relative_to(RAIZ)))
def test_links_relativos_apontam_para_algo_que_existe(arquivo: Path):
    problemas = [p for alvo in _alvos(arquivo) if (p := _confere(arquivo, alvo))]
    assert not problemas, f"links quebrados em {arquivo.relative_to(RAIZ)}:\n" + "\n".join(problemas)


def test_a_verificacao_enxerga_um_link_quebrado(tmp_path: Path):
    """Sem isto, um regex que parasse de casar deixaria o teste acima passar vazio."""
    doc = tmp_path / "a.md"
    doc.write_text("# Título\n\n[ok](#título) [ruim](nao-existe.md) [ancora](#outro)\n", encoding="utf-8")
    assert [_confere(doc, a) is not None for a in _alvos(doc)] == [False, True, True]
