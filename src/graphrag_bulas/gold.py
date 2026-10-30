"""Gold set de extração anotado à mão (E2.5).

Uso:
  uv run python -m graphrag_bulas.gold preparar   # cria data/gold/<bula>.json a partir dos chunks
  uv run python -m graphrag_bulas.gold validar    # confere as anotações contra o schema

`preparar` nunca sobrescreve um arquivo existente: as anotações são trabalho manual.
Formato e regras de anotação em data/gold/LEIAME.md.
"""

import json
import sys
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS

GOLD = Path(__file__).resolve().parents[2] / "data" / "gold"
BULAS = ["cozaar", "marevan", "advil", "renitec", "aspirina"]

# Espelha docs/modelagem.md, seções 3 e 4.
LABELS = {
    "Medicamento", "PrincipioAtivo", "ClasseTerapeutica", "Condicao",
    "EfeitoAdverso", "Fabricante", "Populacao",
}
POPULACOES = {"gestante", "lactante", "pediatrico", "idoso"}
RELACOES = {  # tipo -> (labels de origem, labels de destino)
    "CONTEM": ({"Medicamento"}, {"PrincipioAtivo"}),
    "PERTENCE_A": ({"PrincipioAtivo"}, {"ClasseTerapeutica"}),
    "INDICADO_PARA": ({"Medicamento"}, {"Condicao"}),
    "CONTRAINDICADO_EM": ({"Medicamento"}, {"Condicao", "Populacao"}),
    "PODE_CAUSAR": ({"Medicamento"}, {"EfeitoAdverso"}),
    "INTERAGE_COM": ({"PrincipioAtivo"}, {"PrincipioAtivo", "ClasseTerapeutica"}),
    "FABRICADO_POR": ({"Medicamento"}, {"Fabricante"}),
}
VOCAB = {
    "frequencia": {"muito_comum", "comum", "incomum", "rara", "muito_rara", "desconhecida"},
    "gravidade": {"grave", "moderada", "leve", "desconhecida"},
}


def preparar() -> None:
    chunks = [json.loads(linha) for linha in (PROCESSADOS / "chunks.jsonl").open()]
    GOLD.mkdir(parents=True, exist_ok=True)
    for med in BULAS:
        arq = GOLD / f"bula_{med}.json"
        if arq.exists():
            print(f"{arq.name}: já existe, mantido")
            continue
        doc = {
            "bula": f"bula_{med}",
            "anotador": None,
            "chunks": [
                {
                    "id": c["id"], "tipo": c["tipo"], "texto": c["texto"],
                    # o medicamento da bula já vem como origem mais comum das relações
                    "entidades": [{"id": med, "label": "Medicamento", "nome": med.capitalize()}],
                    "relacoes": [],
                }
                for c in chunks if c["bula"] == f"bula_{med}"
            ],
        }
        arq.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        print(f"{arq.name}: {len(doc['chunks'])} chunks")


def erros(doc: dict) -> list[str]:
    """Lista problemas de uma bula anotada; vazio = válida."""
    out = []
    for c in doc["chunks"]:
        onde = c["id"]
        ents = {}
        for e in c["entidades"]:
            if e.get("label") not in LABELS:
                out.append(f"{onde}: label inválido {e.get('label')!r} em {e.get('id')!r}")
            if not e.get("id") or e["id"] != e["id"].lower() or not e["id"].isascii():
                out.append(f"{onde}: id {e.get('id')!r} deve ser slug minúsculo sem acento")
            if e.get("label") == "Populacao" and e.get("id") not in POPULACOES:
                out.append(f"{onde}: Populacao {e.get('id')!r} fora de {sorted(POPULACOES)}")
            ents[e.get("id")] = e.get("label")
        for r in c["relacoes"]:
            tipo = r.get("tipo")
            if tipo not in RELACOES:
                out.append(f"{onde}: relação inválida {tipo!r}")
                continue
            origens, destinos = RELACOES[tipo]
            for ponta, aceitos in (("origem", origens), ("destino", destinos)):
                eid = r.get(ponta)
                if eid not in ents:
                    out.append(f"{onde}: {tipo}.{ponta} {eid!r} não está em entidades")
                elif ents[eid] not in aceitos:
                    out.append(f"{onde}: {tipo}.{ponta} {eid!r} é {ents[eid]}, esperado {aceitos}")
            for prop, valor in r.get("props", {}).items():
                if prop in VOCAB and valor not in VOCAB[prop]:
                    out.append(f"{onde}: {tipo}.{prop}={valor!r} fora de {sorted(VOCAB[prop])}")
    return out


def validar() -> int:
    total = 0
    for arq in sorted(GOLD.glob("bula_*.json")):
        doc = json.loads(arq.read_text())
        probs = erros(doc)
        n_rel = sum(len(c["relacoes"]) for c in doc["chunks"])
        print(f"{arq.name}: {n_rel} relações, {len(probs)} erros")
        for p in probs:
            print(f"  {p}")
        total += len(probs)
    return 1 if total else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "preparar":
        preparar()
    elif cmd == "validar":
        sys.exit(validar())
    else:
        sys.exit(__doc__)
