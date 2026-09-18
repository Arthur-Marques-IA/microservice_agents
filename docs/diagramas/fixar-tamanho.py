"""Grava o tamanho real (do viewBox) na raiz de cada SVG gerado pelo mermaid-cli.

O mermaid-cli gera `width="100%"` sem altura, e o GitHub então estica a imagem
até a largura da coluna. Com `width`/`height` fixos, cada diagrama aparece no
tamanho natural e só encolhe em telas estreitas.
"""

import pathlib
import re

for svg in sorted(pathlib.Path(__file__).parent.glob("*.svg")):
    text = svg.read_text(encoding="utf-8")
    root = re.search(r"<svg[^>]*>", text).group(0)
    _, _, width, height = (float(n) for n in re.search(r'viewBox="([^"]+)"', root).group(1).split())
    fixed = re.sub(r'\swidth="[^"]*"', "", root)
    fixed = re.sub(r'\sheight="[^"]*"', "", fixed)
    fixed = re.sub(r"max-width:\s*[\d.]+px;?\s*", "", fixed)
    fixed = fixed.replace("<svg", f'<svg width="{round(width)}" height="{round(height)}"', 1)
    svg.write_text(text.replace(root, fixed, 1), encoding="utf-8", newline="\n")
    print(f"{svg.name}: {round(width)}x{round(height)}")
