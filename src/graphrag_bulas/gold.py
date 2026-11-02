"""Gold set de extração anotado à mão (E2.5).

Uso:
  uv run python -m graphrag_bulas.gold preparar   # cria data/gold/<bula>.json a partir dos chunks
  uv run python -m graphrag_bulas.gold validar    # confere as anotações contra o schema
  uv run python -m graphrag_bulas.gold avaliar    # P/R/F1 da extração vs gold (E3.5)

`preparar` nunca sobrescreve um arquivo existente: as anotações são trabalho manual.
Formato e regras de anotação em data/gold/LEIAME.md.

`avaliar` compara por chunk, micro-médias, só chunks presentes no gold, em dois níveis: estrito
(ids exatos) e normalizado (ids passam por resolucao.normalizar + dicionário). Chave de relação =
(tipo, origem, destino); de entidade = (label, id); props são ignoradas. Sem itens, precisão,
recall e F1 valem 0.0 (convenção). Relatório em logs/avaliacao_e3.md.
"""

import json
import sys
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS, slug
from graphrag_bulas.modelos import LABELS, POPULACOES, RELACOES, VOCAB
from graphrag_bulas.resolucao import carregar_dicionario, normalizar

GOLD = Path(__file__).resolve().parents[2] / "data" / "gold"
BULAS = ["cozaar", "marevan", "advil", "renitec", "aspirina"]


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
                    "id": c["id"],
                    "tipo": c["tipo"],
                    "texto": c["texto"],
                    # o medicamento da bula já vem como origem mais comum das relações
                    "entidades": [{"id": med, "label": "Medicamento", "nome": med.capitalize()}],
                    "relacoes": [],
                }
                for c in chunks
                if c["bula"] == f"bula_{med}"
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


def _chaves(chunk: dict, normalizado: bool, dic: dict) -> tuple[set, set]:
    """(entidades, relações) de um chunk como conjuntos de chaves comparáveis."""
    labels = {e["id"]: e["label"] for e in chunk.get("entidades", [])}

    def chave(id_, label):
        if not normalizado:
            return (label, id_)
        if label is None:  # ponta fora da lista de entidades: só o slug
            return (None, slug(id_))
        n = normalizar(id_, label)
        return (label, dic.get(label, {}).get(n, n))

    ents = {chave(e["id"], e["label"]) for e in chunk.get("entidades", [])}
    rels = {
        (
            r["tipo"],
            chave(r["origem"], labels.get(r["origem"])),
            chave(r["destino"], labels.get(r["destino"])),
        )
        for r in chunk.get("relacoes", [])
    }
    return ents, rels


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precisao": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p + r else 0.0,
    }


def avaliar_docs(gold_docs, extracoes, normalizar_ids: bool, dic: dict | None = None) -> dict:
    """Métricas micro de entidades e relações (+ por tipo de relação e por bula)."""
    if dic is None:
        dic = carregar_dicionario() if normalizar_ids else {}
    por_chunk = {x["chunk_id"]: x for x in extracoes}
    soma = {k: [0, 0, 0] for k in ("entidades", "relacoes")}
    por_tipo, por_bula = {}, {}
    for doc in gold_docs:
        for c in doc["chunks"]:
            ge, gr = _chaves(c, normalizar_ids, dic)
            ee, er = _chaves(por_chunk.get(c["id"], {}), normalizar_ids, dic)
            for k, (g, e) in {"entidades": (ge, ee), "relacoes": (gr, er)}.items():
                for i, n in enumerate((len(g & e), len(e - g), len(g - e))):
                    soma[k][i] += n
            for t in {r[0] for r in gr | er}:
                acc = por_tipo.setdefault(t, [0, 0, 0])
                for i, n in enumerate(
                    (
                        len({r for r in gr & er if r[0] == t}),
                        len({r for r in er - gr if r[0] == t}),
                        len({r for r in gr - er if r[0] == t}),
                    )
                ):
                    acc[i] += n
            acc = por_bula.setdefault(doc["bula"], [0, 0, 0])
            for i, n in enumerate((len(gr & er), len(er - gr), len(gr - er))):
                acc[i] += n
    return {
        "entidades": _prf(*soma["entidades"]),
        "relacoes": _prf(*soma["relacoes"]),
        "por_tipo": {t: _prf(*v) for t, v in sorted(por_tipo.items())},
        "por_bula": {b: _prf(*v) for b, v in sorted(por_bula.items())},
    }


def _linha(nome: str, m: dict) -> str:
    cels = [m["tp"], m["fp"], m["fn"], *(f"{m[k]:.3f}" for k in ("precisao", "recall", "f1"))]
    return f"| {nome} | " + " | ".join(map(str, cels)) + " |"


CAB = "| | TP | FP | FN | P | R | F1 |\n|---|---|---|---|---|---|---|"


def avaliar() -> int:
    docs = [json.loads(a.read_text(encoding="utf-8")) for a in sorted(GOLD.glob("bula_*.json"))]
    extr = [
        json.loads(x)
        for x in (PROCESSADOS / "extracoes.jsonl").read_text(encoding="utf-8").splitlines()
        if x
    ]
    avisos = [
        f"{d['bula']}: anotador {d.get('anotador')!r} (rascunho/vazio)"
        for d in docs
        if not d.get("anotador") or "rascunho" in d["anotador"].lower()
    ] + [
        f"{d['bula']}: 0 relações no gold"
        for d in docs
        if not sum(len(c["relacoes"]) for c in d["chunks"])
    ]
    est, nor = avaliar_docs(docs, extr, False), avaliar_docs(docs, extr, True)
    linhas = ["# Avaliação da extração contra o gold (E3.5)", ""]
    if avisos:
        linhas += [
            "**AVISO: números preliminares até a revisão humana do gold.** " + "; ".join(avisos),
            "",
        ]
    linhas += [f"Chunks avaliados: {sum(len(d['chunks']) for d in docs)}", "", "## Geral", CAB]
    for nivel, m in (("estrito", est), ("normalizado", nor)):
        linhas += [
            _linha(f"relações ({nivel})", m["relacoes"]),
            _linha(f"entidades ({nivel})", m["entidades"]),
        ]
    for titulo, chave in (
        ("Relações por tipo (normalizado)", "por_tipo"),
        ("Relações por bula (normalizado)", "por_bula"),
    ):
        linhas += ["", f"## {titulo}", CAB] + [_linha(k, v) for k, v in nor[chave].items()]
    texto = "\n".join(linhas) + "\n"
    saida = Path(__file__).resolve().parents[2] / "logs" / "avaliacao_e3.md"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "preparar":
        preparar()
    elif cmd == "validar":
        sys.exit(validar())
    elif cmd == "avaliar":
        sys.exit(avaliar())
    else:
        sys.exit(__doc__)
