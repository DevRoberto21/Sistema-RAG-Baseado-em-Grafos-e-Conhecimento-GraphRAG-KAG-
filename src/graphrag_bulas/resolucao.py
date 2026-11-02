"""Resolução de entidades (E4.1, E4.2): extracoes.jsonl -> grafo.jsonl.

Uso:
  uv run --extra embeddings python -m graphrag_bulas.resolucao

Três passos por label: regra (normalizar), dicionário curado (data/curadoria/sinonimos.json)
e similaridade de embedding com limiar. Grava data/processed/grafo.jsonl,
logs/pares_candidatos.csv e a primeira parte de logs/relatorio_e4.md.
Spec: docs/superpowers/specs/2026-11-01-e4-resolucao-ingestao-design.md
"""

import csv
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS, slug
from graphrag_bulas.extracao import COMPOSICAO

log = logging.getLogger(__name__)

RAIZ = PROCESSADOS.parents[1]
DICIONARIO = RAIZ / "data" / "curadoria" / "sinonimos.json"
ROTULADOS = RAIZ / "data" / "curadoria" / "pares_rotulados.csv"
ENTRADA = PROCESSADOS / "extracoes.jsonl"
SAIDA = PROCESSADOS / "grafo.jsonl"
PARES = RAIZ / "logs" / "pares_candidatos.csv"
RELATORIO = RAIZ / "logs" / "relatorio_e4.md"

LIMIAR_PADRAO = 0.92
FAIXA_PARES = (0.80, 0.95)
SEM_EMBEDDING = {"Medicamento", "Populacao", "Fabricante"}  # vocabulário fechado

GRAFIA = {
    "inhibidor": "inibidor",
    "inhibidores": "inibidores",
    "sistematico": "sistemico",
    "sistematicos": "sistemicos",
}
SAL_PREFIXO = re.compile(
    r"^(cloridrato|dicloridrato|maleato|carbonato|besilato|sulfato|fosfato|succinato|"
    r"tartarato|acetato|citrato|mesilato)_de_"
)
SAL_SUFIXO = re.compile(
    r"_(potassica|potassico|sodica|sodico|calcica|calcico|magnesica|medoxomila|"
    r"monoidratad[ao]|di_?hidratad[ao]|tri_?hidratad[ao])$"
)
OPOSTOS = [("hiper", "hipo"), ("bradi", "taqui"), ("aumento", "diminuicao"), ("aumento", "reducao")]


def _singular(p: str) -> str:
    if p.endswith(("res", "zes")):
        return p[:-2]
    if p.endswith("ais"):
        return p[:-3] + "al"
    if p.endswith("s") and not p.endswith("ss") and len(p) > 2:
        return p[:-1]
    return p


def normalizar(id_: str, label: str) -> str:
    """Regras do E4.1: grafia; sal em PrincipioAtivo; singular em ClasseTerapeutica."""
    partes = [GRAFIA.get(p, p) for p in slug(id_).split("_")]
    if label == "ClasseTerapeutica":
        partes = [_singular(p) for p in partes]
    id_ = "_".join(partes)
    if label == "PrincipioAtivo":
        id_ = SAL_SUFIXO.sub("", SAL_PREFIXO.sub("", id_))
    return id_


def bloqueado(a: str, b: str) -> bool:
    """Nomes com prefixo de sentido oposto (hipertensao/hipotensao) nunca se fundem."""
    return any((x in a and y in b) or (y in a and x in b) for x, y in OPOSTOS)


def carregar_dicionario(path: Path = DICIONARIO) -> dict[str, dict[str, str]]:
    """{label: {variante normalizada: id canônico}}. Inclui nome comercial -> princípio ativo."""
    bruto = json.loads(path.read_text(encoding="utf-8"))
    bruto.setdefault("PrincipioAtivo", {})
    for med, pas in COMPOSICAO.items():
        if len(pas) == 1:
            bruto["PrincipioAtivo"].setdefault(pas[0], []).append(med)
    dic = {}
    for label, grupos in bruto.items():
        dic[label] = {}
        for canon, variantes in grupos.items():
            for v in [canon, *variantes]:
                dic[label][normalizar(v, label)] = canon
    return dic


def _cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # vetores já normalizados


def agrupar(itens, canonicos, vetores, limiar):
    """Funde ids parecidos de um label. Devolve ({id: representante}, fusões, pares).

    itens: {id: frequência}; canonicos: ids do dicionário; vetores: {id: vetor normalizado}.
    Ordem: canônicos primeiro, depois os mais frequentes; cada id vai para o representante mais
    parecido já visto, se o cosseno passa do limiar e o par não é bloqueado. Dois canônicos
    nunca se fundem. fusões: [(de, para, cos)]; pares: [(id, representante, cos)] na FAIXA_PARES.
    """
    ordem = sorted(itens, key=lambda i: (i not in canonicos, -itens[i], i))
    mapa, reps, fusoes, pares = {}, [], [], []
    for i in ordem:
        melhor, cos = None, -1.0
        for r in reps:
            if bloqueado(i, r) or (i in canonicos and r in canonicos):
                continue
            c = _cos(vetores[i], vetores[r])
            if c > cos:
                melhor, cos = r, c
        if melhor and FAIXA_PARES[0] <= cos < FAIXA_PARES[1]:
            pares.append((i, melhor, cos))
        if melhor and cos >= limiar:
            mapa[i] = melhor
            fusoes.append((i, melhor, cos))
        else:
            mapa[i] = i
            reps.append(i)
    return mapa, fusoes, pares


def escolher_limiar(rotulados, alvo=0.95, padrao=LIMIAR_PADRAO) -> float:
    """Menor cosseno de corte com precisão >= alvo nos pares rotulados [(cos, mesmo)]."""
    for t in sorted({c for c, _ in rotulados}):
        acima = [m for c, m in rotulados if c >= t]
        if sum(acima) / len(acima) >= alvo:
            return t
    return padrao


def ler_rotulados(path: Path = ROTULADOS):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return [
            (float(r["cosseno"]), r["mesmo"].strip().lower() == "s")
            for r in csv.DictReader(f)
            if r["mesmo"].strip()
        ]


@dataclass
class Resolucao:
    nos: list[dict]
    rels: list[dict]
    antes: Counter
    passos: Counter = field(default_factory=Counter)  # (label, passo) -> ids fundidos
    fusoes: list = field(default_factory=list)  # (label, de, para, cos)
    pares: list = field(default_factory=list)  # (label, id, representante, cos)
    rels_antes: Counter = field(default_factory=Counter)
    lacos: int = 0
    unicos: list = field(default_factory=list)  # (label, id) visto 1 vez e sem fusão


def resolver(linhas, dicionario, embed, limiar) -> Resolucao:
    """Resolve as entidades de extracoes.jsonl e junta as relações repetidas.

    embed(textos) -> vetores normalizados (embeddings.embed nos scripts; falso nos testes).
    """
    freq, nomes = Counter(), defaultdict(Counter)
    for linha in linhas:
        for e in linha["entidades"]:
            freq[e["label"], e["id"]] += 1
            nomes[e["label"], e["id"]][e["nome"]] += 1
    antes = Counter(label for label, _ in freq)

    res = Resolucao(nos=[], rels=[], antes=antes)
    passo1 = {}
    for label, i in freq:
        n = normalizar(i, label)
        d = dicionario.get(label, {}).get(n, n)
        passo1[label, i] = d
        if n != i:
            res.passos[label, "regra"] += 1
        if d != n:
            res.passos[label, "dicionario"] += 1

    por_label = defaultdict(Counter)
    nomes2 = defaultdict(Counter)
    for (label, i), d in passo1.items():
        por_label[label][d] += freq[label, i]
        nomes2[label, d].update(nomes[label, i])

    final = {}
    for label, itens in por_label.items():
        if label in SEM_EMBEDDING:
            final.update({(label, d): d for d in itens})
            continue
        ids = sorted(itens)
        textos = [nomes2[label, d].most_common(1)[0][0] for d in ids]
        vetores = dict(zip(ids, embed(textos), strict=True))
        canonicos = set(dicionario.get(label, {}).values())
        mapa, fusoes, pares = agrupar(itens, canonicos, vetores, limiar)
        final.update({(label, d): r for d, r in mapa.items()})
        res.passos[label, "embedding"] += len(fusoes)
        res.fusoes += [(label, *f) for f in fusoes]
        res.pares += [(label, *p) for p in pares]
        fundidos = {f[0] for f in fusoes} | {f[1] for f in fusoes}
        res.unicos += [(label, d) for d in ids if itens[d] == 1 and d not in fundidos]

    agrupados = defaultdict(Counter)
    for (label, d), r in final.items():
        agrupados[label, r].update(nomes2[label, d])
    for (label, r), cont in sorted(agrupados.items()):
        # nome que contradiz o id por prefixo oposto (hipo/hiper) não vale
        ok = Counter({n: c for n, c in cont.items() if not bloqueado(r, slug(n))})
        nome = ok.most_common(1)[0][0] if ok else r.replace("_", " ").capitalize()
        res.nos.append(
            {
                "tipo": "no",
                "label": label,
                "id": r,
                "nome": nome,
                "sinonimos": sorted(n for n in ok if n != nome),
            }
        )

    def mapear(label, i):
        return final[label, passo1[label, i]]

    rels = {}
    for linha in linhas:
        labels = {e["id"]: e["label"] for e in linha["entidades"]}
        for r in linha["relacoes"]:
            res.rels_antes[r["tipo"]] += 1
            lo, ld = labels[r["origem"]], labels[r["destino"]]
            o, d = mapear(lo, r["origem"]), mapear(ld, r["destino"])
            if (lo, o) == (ld, d):
                res.lacos += 1
                continue
            chave = (r["tipo"], lo, o, ld, d)
            props = {p: r.get(p) for p in ("frequencia", "gravidade", "efeito", "dose")}
            nova = {
                "tipo": "rel",
                "rel": r["tipo"],
                "label_origem": lo,
                "origem": o,
                "label_destino": ld,
                "destino": d,
                **props,
                "confianca": r["confianca"],
                "fonte_chunk_id": linha["chunk_id"],
                "chunks": [linha["chunk_id"]],
            }
            atual = rels.get(chave)
            if atual is None:
                rels[chave] = nova
                continue
            chunks = sorted({*atual["chunks"], linha["chunk_id"]})
            if nova["confianca"] > atual["confianca"]:
                rels[chave] = nova
            rels[chave]["chunks"] = chunks
    res.rels = list(rels.values())
    return res


def relatorio(res: Resolucao, limiar: float, fonte_limiar: str) -> str:
    depois = Counter(n["label"] for n in res.nos)
    rels_depois = Counter(r["rel"] for r in res.rels)
    linhas = [
        "# Relatório E4 — resolução e ingestão",
        "",
        f"Limiar de embedding: {limiar:.3f} ({fonte_limiar}).",
        "",
        "## Nós por label",
        "",
        "| Label | Antes | Depois | Regra | Dicionário | Embedding |",
        "|---|---|---|---|---|---|",
    ]
    for label in sorted(res.antes):
        linhas.append(
            f"| {label} | {res.antes[label]} | {depois[label]} | "
            f"{res.passos[label, 'regra']} | {res.passos[label, 'dicionario']} | "
            f"{res.passos[label, 'embedding']} |"
        )
    linhas += ["", "## Relações por tipo", "", "| Tipo | Antes | Depois |", "|---|---|---|"]
    for tipo in sorted(res.rels_antes):
        linhas.append(f"| {tipo} | {res.rels_antes[tipo]} | {rels_depois[tipo]} |")
    linhas += [
        "",
        f"Relações descartadas por laço depois da fusão: {res.lacos}.",
        "",
        "## 30 maiores fusões por embedding",
        "",
        "| Label | De | Para | Cosseno |",
        "|---|---|---|---|",
    ]
    for label, de, para, cos in sorted(res.fusoes, key=lambda f: -f[3])[:30]:
        linhas.append(f"| {label} | {de} | {para} | {cos:.3f} |")
    linhas += ["", f"## Ids vistos uma vez e sem fusão ({len(res.unicos)})", ""]
    linhas += [f"- {label}: {i}" for label, i in sorted(res.unicos)]
    return "\n".join(linhas) + "\n"


def main():
    from graphrag_bulas.embeddings import embed

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    linhas = [json.loads(x) for x in ENTRADA.open(encoding="utf-8")]
    rotulados = ler_rotulados()
    if rotulados:
        limiar, fonte = escolher_limiar(rotulados), f"{len(rotulados)} pares rotulados"
    else:
        limiar, fonte = LIMIAR_PADRAO, "padrão; sem data/curadoria/pares_rotulados.csv"
        log.warning("sem pares rotulados: limiar padrão %.2f", limiar)
    res = resolver(linhas, carregar_dicionario(), embed, limiar)

    tmp = SAIDA.with_name(SAIDA.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for item in [*res.nos, *res.rels]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    tmp.replace(SAIDA)
    PARES.parent.mkdir(exist_ok=True)
    with PARES.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "id_a", "id_b", "cosseno", "mesmo"])
        for label, a, b, cos in sorted(res.pares, key=lambda p: -p[3]):
            w.writerow([label, a, b, f"{cos:.4f}", ""])
    RELATORIO.write_text(relatorio(res, limiar, fonte), encoding="utf-8")
    print(
        f"{SAIDA.name}: {len(res.nos)} nós, {len(res.rels)} relações; "
        f"{len(res.pares)} pares candidatos; relatório em {RELATORIO}"
    )


if __name__ == "__main__":
    main()
