"""Chunking por seção com IDs estáveis (E2.4).

Uso: uv run python -m graphrag_bulas.chunks
Lê data/processed/secoes.jsonl (E2.3) e grava data/processed/chunks.jsonl,
um chunk por linha. IDs seguem docs/modelagem.md: bula_<med>_<secao>_<ordem>.
"""

import json
import re
import unicodedata
from pathlib import Path

PROCESSADOS = Path(__file__).resolve().parents[2] / "data" / "processed"
MAX_CHARS = 1200

# Seção do parser -> Secao.tipo do schema. As demais seções ficam fora do grafo.
TIPOS = {
    "indicacoes": "indicacoes",
    "contraindicacoes": "contraindicacoes",
    "advertencias_precaucoes": "advertencias",
    "interacoes": "interacoes",
    "reacoes_adversas": "reacoes_adversas",
    "posologia": "posologia",
}
# Fim de frase seguido de início de frase/item.
RE_FRASE = re.compile(r"(?<=[.;:])\s+(?=[A-ZÀ-Ú0-9•\-–(])")


def slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def bula_id(arquivo: str) -> str:
    """bula_Puran T4.pdf -> bula_puran_t4 (igual a 'bula_' + id do medicamento)."""
    return "bula_" + slug(Path(arquivo).stem.removeprefix("bula_"))


def quebrar(texto: str, limite: int = MAX_CHARS) -> list[str]:
    """Agrupa frases inteiras até `limite` caracteres; frase maior é cortada por palavra."""
    texto = re.sub(r"\s+", " ", texto).strip()
    pedacos, atual = [], ""
    for frase in RE_FRASE.split(texto):
        while len(frase) > limite:  # tabela ou frase gigante
            corte = frase.rfind(" ", 0, limite)
            corte = corte if corte > 0 else limite
            if atual:
                pedacos.append(atual)
                atual = ""
            pedacos.append(frase[:corte])
            frase = frase[corte:].lstrip()
        if atual and len(atual) + 1 + len(frase) > limite:
            pedacos.append(atual)
            atual = frase
        else:
            atual = f"{atual} {frase}" if atual else frase
    if atual:
        pedacos.append(atual)
    return pedacos


def chunks_da_bula(bula: dict) -> list[dict]:
    b = bula_id(bula["arquivo"])
    saida = []
    for chave, tipo in TIPOS.items():
        secao = f"{b}_{tipo}"
        for ordem, texto in enumerate(quebrar(bula["secoes"].get(chave, ""))):
            saida.append({
                "id": f"{secao}_{ordem}", "bula": b, "secao": secao,
                "tipo": tipo, "ordem": ordem, "texto": texto,
            })
    return saida


def main() -> None:
    bulas = map(json.loads, (PROCESSADOS / "secoes.jsonl").read_text().splitlines())
    chunks = [c for bula in bulas for c in chunks_da_bula(bula)]
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)), "id de chunk duplicado"
    (PROCESSADOS / "chunks.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)
    )
    print(f"{len(chunks)} chunks em {PROCESSADOS / 'chunks.jsonl'}")


if __name__ == "__main__":
    main()
