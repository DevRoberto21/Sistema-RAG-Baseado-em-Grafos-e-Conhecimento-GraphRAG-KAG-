"""Parser bula PDF -> texto separado por seção (E2.3).

Uso: uv run python -m graphrag_bulas.secoes
Lê data/raw/*.pdf (requer `pdftotext`, do poppler) e grava
data/processed/secoes.jsonl, uma bula por linha.

Segue os 10 itens numerados da bula do profissional (RDC 47/2009).
"""

import json
import re
import subprocess
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2] / "data"
SAIDA = RAIZ / "processed" / "secoes.jsonl"

# (chave, número do item, início do título). Títulos longos podem quebrar linha,
# então só a 1ª palavra é exigida quando ela já é distintiva.
SECOES = [
    ("indicacoes", 1, r"INDICA[CÇ][OÕ]ES"),
    ("resultados_eficacia", 2, r"RESULTADOS?\s+D?E\s+EFIC"),
    ("caracteristicas_farmacologicas", 3, r"CARACTER[IÍ]STICAS"),
    ("contraindicacoes", 4, r"CONTRA-?\s*INDICA"),
    ("advertencias_precaucoes", 5, r"ADVERT[EÊ]NCIAS"),
    ("interacoes", 6, r"INTERA[CÇ][OÕ]ES"),
    ("armazenamento", 7, r"CUIDADOS\s+DE"),
    ("posologia", 8, r"POSOLOGIA"),
    ("reacoes_adversas", 9, r"REA[CÇ][OÕ]ES"),
    ("superdose", 10, r"SUPERDOS"),
]
# Título = linha inteira em maiúsculas, com ou sem "N." na frente (case-sensitive:
# remissões no corpo, como "(veja 9. REAÇÕES ADVERSAS).", ficam de fora).
TITULOS = [
    (chave, re.compile(rf"^[ \t]*(?:{n}\s*[.)\-]?\s*)?(?:{kw})[A-ZÀ-Ú \t/\-:]*$", re.M))
    for chave, n, kw in SECOES
]
# Fim da última seção: dizeres legais, histórico ou a bula da próxima apresentação.
RE_FIM = re.compile(r"DIZERES\s+LEGAIS|hist[oó]rico\s+de\s+altera|^[ \t]*1\.\s*INDICA", re.I | re.M)
# A tabela de histórico no fim repete os nomes dos itens; corta antes dela.
RE_HISTORICO = re.compile(r"hist[oó]rico\s+de\s+altera", re.I)
# Ruído de cabeçalho/rodapé: números de página soltos e quebras de página.
RE_RUIDO = re.compile(r"^[ \t]*(?:-?\s*\d+\s*(?:de\s+\d+\s*)?-?)?[ \t]*$", re.M)


def texto(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True
    ).stdout


def limpar(s: str) -> str:
    s = RE_RUIDO.sub("", s)
    return re.sub(r"\n{2,}", "\n", s).strip()


def separar(txt: str) -> dict[str, str]:
    """Mapeia chave -> texto da seção. Seção não encontrada fica de fora.

    Busca os títulos em ordem, cada um depois do anterior, e corta cada seção
    no próximo título encontrado (ou em RE_FIM).
    """
    # Alguns PDFs trazem acentos decompostos (NFD), que não casam com "Ç"/"Õ".
    # Quebra de página (\f) cola no título seguinte e esconde o início da linha.
    txt = unicodedata.normalize("NFC", txt).replace("\f", "\n")
    if h := RE_HISTORICO.search(txt):
        txt = txt[: h.start()]
    achados = []  # (chave, início do título, fim do título)
    pos = 0
    for chave, rx in TITULOS:
        if m := rx.search(txt, pos):
            achados.append((chave, m.start(), m.end()))
            pos = m.end()
    if achados and (f := RE_FIM.search(txt, pos)):
        txt = txt[: f.start()]
    secoes = {}
    for i, (chave, _, fim) in enumerate(achados):
        proximo = achados[i + 1][1] if i + 1 < len(achados) else len(txt)
        secoes[chave] = limpar(txt[fim:proximo])
    return secoes


def main() -> None:
    manifesto = {
        e["arquivo"]: e
        for e in map(json.loads, (RAIZ / "raw" / "manifesto.jsonl").read_text().splitlines())
    }
    linhas = []
    for pdf in sorted((RAIZ / "raw").glob("*.pdf"), key=lambda p: p.name.lower()):
        secoes = separar(texto(pdf))
        faltando = [c for c, _ in TITULOS if not secoes.get(c)]
        if faltando:
            print(f"{pdf.name}: sem {', '.join(faltando)}")
        meta = manifesto.get(pdf.name, {})
        linhas.append(json.dumps({
            "arquivo": pdf.name,
            "medicamento": meta.get("medicamento", pdf.stem.removeprefix("bula_").upper()),
            "secoes": secoes,
        }, ensure_ascii=False))
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text("\n".join(linhas) + "\n")
    print(f"{len(linhas)} bulas em {SAIDA}")


if __name__ == "__main__":
    main()
