"""Avaliação GraphRAG vs baselines (E7): gold de perguntas, rodada e relatório.

Spec: docs/superpowers/specs/2026-11-02-e7-avaliacao-design.md
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from graphrag_bulas.chunks import PROCESSADOS, slug
from graphrag_bulas.geracao import RECUSA, Resposta

CONTAGEM = {"1hop": 15, "multihop": 15, "sem_resposta": 10}


def cobertura(resposta, fatos):
    """Fração dos fatos com alguma variante dentro da resposta (slug dos dois lados)."""
    r = slug(resposta)
    return sum(any(slug(v) in r for v in fato) for fato in fatos) / len(fatos)


def metricas(pergunta, linha):
    """Métricas de uma resposta; None se a linha tem erro."""
    if linha["erro"]:
        return None
    if pergunta["tipo"] == "sem_resposta":
        return {"recusa_correta": int(linha["recusou"]), "alucinacao": int(not linha["recusou"])}
    cob = 0.0 if linha["recusou"] else cobertura(linha["resposta"], pergunta["fatos"])
    citados = linha["citados"]
    fid = (sum(c in pergunta["fontes"] for c in citados) / len(citados)) if citados else None
    return {"cobertura": cob, "acerto": int(cob == 1.0), "recusa_falsa": int(linha["recusou"]),
            "fidelidade": fid}


def validar_gold(gold, chunk_ids):
    """Erros do gold de perguntas: ids, contagem por tipo, fatos/fontes e fontes inexistentes."""
    ps = gold["perguntas"]
    erros = [f"id repetido: {i}" for i, n in Counter(p["id"] for p in ps).items() if n > 1]
    tipos = Counter(p["tipo"] for p in ps)
    erros += [f"{t}: {tipos[t]} perguntas, esperado {n}" for t, n in CONTAGEM.items()
              if tipos[t] != n]
    for p in ps:
        tem = bool(p["fatos"]) and bool(p["fontes"])
        if (p["tipo"] == "sem_resposta") == tem:
            erros.append(f"{p['id']}: fatos/fontes não batem com o tipo {p['tipo']}")
        erros += [f"{p['id']}: fonte {c} não existe" for c in p["fontes"] if c not in chunk_ids]
    return erros
RAIZ = Path(__file__).resolve().parents[2]
GOLD = RAIZ / "data" / "gold" / "perguntas.json"
RESPOSTAS = RAIZ / "logs" / "e7" / "respostas.jsonl"
RELATORIO = RAIZ / "logs" / "avaliacao_e7.md"
MODOS = ("graphrag", "rag", "llm_puro")

PROMPT_PURO = """Você responde perguntas sobre medicamentos, em português, com o seu conhecimento.
Não há contexto nem trechos de bula: use só o que você sabe. Deixe chunks e nos vazios.
suporte: total se você sabe a resposta, parcial se sabe só parte, nenhum só se não sabe.
Em pergunta sobre interação, contraindicação ou dose, oriente procurar médico ou farmacêutico.

Pergunta: {pergunta}"""


def responder_llm_puro(llm, pergunta):
    """Baseline sem contexto (E7.3): mesmo LLM e mesmo schema de resposta do E5.6."""
    r = llm.with_structured_output(Resposta).invoke(PROMPT_PURO.format(pergunta=pergunta))
    recusou = r.suporte == "nenhum"
    return {"resposta": RECUSA if recusou else r.resposta, "recusou": recusou,
            "confianca": 0.0 if recusou else None, "trechos": []}


def rodar(perguntas, modos, responder, saida):
    """Uma linha por (pergunta, modo) em saida; pula o que já deu certo. Devolve linhas novas."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    feitos = set()
    if saida.exists():
        feitos = {(x["id"], x["modo"]) for x in map(json.loads, saida.read_text().splitlines())
                  if not x["erro"]}
    novas = 0
    with saida.open("a", encoding="utf-8") as f:
        for modo in modos:
            for p in perguntas:
                if (p["id"], modo) in feitos:
                    continue
                t0, linha = time.monotonic(), {"id": p["id"], "modo": modo, "erro": None}
                try:
                    r = responder(p["pergunta"], modo)
                    linha |= {"resposta": r["resposta"], "recusou": r["recusou"],
                              "confianca": r["confianca"],
                              "citados": [t["chunk_id"] for t in r["trechos"] if t.get("citado")]}
                except Exception as e:  # uma pergunta ruim não para a rodada
                    linha |= {"resposta": "", "recusou": False, "confianca": None, "citados": [],
                              "erro": f"{type(e).__name__}: {e}"}
                linha["segundos"] = round(time.monotonic() - t0, 1)
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
                f.flush()
                novas += 1
                print(f"{modo} {p['id']} {linha['segundos']}s {linha['erro'] or ''}", flush=True)
    return novas


def _media(xs):
    xs = [x for x in xs if x is not None]
    return f"{sum(xs) / len(xs):.3f}" if xs else "—"


def relatorio(perguntas, linhas):
    """Markdown com a tabela geral por modo e cobertura/acerto por modo x tipo."""
    por_id = {p["id"]: p for p in perguntas}
    ultima = {(x["id"], x["modo"]): x for x in linhas if x["id"] in por_id}  # última tentativa vale
    modos = [m for m in MODOS if any(k[1] == m for k in ultima)]
    cab = ["cobertura", "acerto", "fidelidade", "recusa_falsa", "recusa_correta", "alucinacao"]
    md = ["# Avaliação GraphRAG vs baselines (E7)", "",
          f"**Perguntas sem revisão humana** (escritas pelo Claude a partir das bulas). "
          f"{len(perguntas)} perguntas.", "", "## Geral",
          "| modo | " + " | ".join(cab) + " | tempo médio (s) | erros |",
          "|---" * (len(cab) + 3) + "|"]
    tipos_md = ["", "## Por tipo", "| modo | tipo | cobertura | acerto |", "|---|---|---|---|"]
    for m in modos:
        ls = [x for k, x in ultima.items() if k[1] == m]
        ms = [(por_id[x["id"]]["tipo"], metricas(por_id[x["id"]], x)) for x in ls]
        ok = [(t, v) for t, v in ms if v is not None]
        cel = [_media(v.get(c) for _, v in ok if c in v) for c in cab]
        tempo = sum(x["segundos"] for x in ls) / len(ls)
        md.append(f"| {m} | " + " | ".join(cel) + f" | {tempo:.1f} | {len(ms) - len(ok)} |")
        for t in ("1hop", "multihop"):
            vs = [v for tt, v in ok if tt == t]
            tipos_md.append(f"| {m} | {t} | {_media(v['cobertura'] for v in vs)} | "
                            f"{_media(v['acerto'] for v in vs)} |")
    return "\n".join(md + tipos_md) + "\n"


def _ler_jsonl(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("comando", choices=["validar", "rodar", "relatorio"])
    p.add_argument("--modo", action="append", choices=MODOS, help="repetível; padrão: os três")
    a = p.parse_args(argv)
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    if a.comando == "validar":
        ids = {c["id"] for c in _ler_jsonl(PROCESSADOS / "chunks.jsonl")}
        erros = validar_gold(gold, ids)
        print("\n".join(erros) or f"ok: {len(gold['perguntas'])} perguntas")
        return 1 if erros else 0
    if a.comando == "relatorio":
        RELATORIO.write_text(relatorio(gold["perguntas"], _ler_jsonl(RESPOSTAS)), encoding="utf-8")
        print(RELATORIO.read_text(encoding="utf-8"))
        return 0
    from graphrag_bulas.api import responder
    from graphrag_bulas.config import get_driver, get_llm

    llm = get_llm(temperature=0)
    with get_driver() as d:
        def resp(pergunta, modo):
            if modo == "llm_puro":
                return responder_llm_puro(llm, pergunta)
            return responder(pergunta, modo, d, llm)

        rodar(gold["perguntas"], a.modo or list(MODOS), resp, RESPOSTAS)
    return 0


if __name__ == "__main__":
    sys.exit(main())