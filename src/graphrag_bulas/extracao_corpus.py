"""Extração NER/RE no corpus inteiro (E3.4), com cache, retry e teto de chamadas.

Uso:
  uv run python -m graphrag_bulas.extracao_corpus --bulas 10   # piloto: 10 primeiras bulas
  uv run python -m graphrag_bulas.extracao_corpus              # corpus inteiro
  caffeinate -i uv run python -m graphrag_bulas.extracao_corpus  # macOS: não dorme no meio
  opções: --bula cozaar (repetível)  --max-chamadas N  --pausa S  --modelo gemini-3.5-flash-lite

Lê data/processed/chunks.jsonl (E2.4) e grava data/processed/extracoes.jsonl, uma linha por
chunk: entidades e relações já validadas (E3.3) e os descartes.

Cache: a resposta crua do LLM fica em data/processed/cache_llm/<chunk>_<hash>.json. O hash cobre
modelo + prompt, então mudar o prompt (E3.5) ou o chunk refaz só o que mudou. Rodar de novo
não gasta cota com o que já está no cache. Chunk que falhou fica fora do cache e da saída;
a próxima rodada tenta de novo.
"""

import argparse
import hashlib
import json
import logging
import time

from graphrag_bulas import config
from graphrag_bulas.chunks import PROCESSADOS
from graphrag_bulas.extracao import extrair, montar_prompt, validar
from graphrag_bulas.modelos import Extracao

log = logging.getLogger(__name__)

CACHE = PROCESSADOS / "cache_llm"
SAIDA = PROCESSADOS / "extracoes.jsonl"
ESPERAS_S = (10, 30, 60)  # 503/504 e 429 por minuto do Gemini são picos passageiros


class CotaDiaria(Exception):
    """Cota por dia esgotada: tentar de novo só gasta tempo até o reset."""


def _cota_diaria(e):
    return "RESOURCE_EXHAUSTED" in str(e) and "PerDay" in str(e)


def caminho_cache(chunk, modelo):
    h = hashlib.sha256(f"{modelo}\n{montar_prompt(chunk)}".encode()).hexdigest()[:12]
    return CACHE / f"{chunk['id']}_{h}.json"


def extrair_com_retry(llm, chunk, esperas=ESPERAS_S, dormir=time.sleep):
    for espera in (*esperas, None):
        try:
            return extrair(llm, chunk)
        except Exception as e:  # rede, cota, 503 ou JSON fora do schema
            if _cota_diaria(e):
                raise CotaDiaria(str(e)) from e
            if espera is None:
                raise
            log.warning("%s: %s; nova tentativa em %ss", chunk["id"], e, espera)
            dormir(espera)


def rodar(chunks, llm, modelo, max_chamadas=None, pausa=0.0, dormir=time.sleep):
    """Extrai e valida cada chunk, usando o cache. Devolve as linhas da saída e as contagens."""
    CACHE.mkdir(parents=True, exist_ok=True)
    linhas, conta = [], {"cache": 0, "chamadas": 0, "falhas": 0, "sem_cota": 0}
    for i, chunk in enumerate(chunks, 1):
        arq = caminho_cache(chunk, modelo)
        if arq.exists():
            bruta = Extracao.model_validate_json(arq.read_text())
            conta["cache"] += 1
        elif max_chamadas is not None and conta["chamadas"] >= max_chamadas:
            conta["sem_cota"] += 1
            continue
        else:
            if conta["chamadas"] and pausa:
                dormir(pausa)
            conta["chamadas"] += 1
            try:
                bruta = extrair_com_retry(llm, chunk, dormir=dormir)
            except CotaDiaria:
                log.error("cota diária do modelo esgotada; parando (o cache guarda o feito)")
                conta["sem_cota"] += len(chunks) - i + 1
                break
            except Exception as e:
                log.error("[%d/%d] %s: desisti: %s", i, len(chunks), chunk["id"], e)
                conta["falhas"] += 1
                continue
            arq.write_text(bruta.model_dump_json())
        limpa, descartes = validar(bruta, chunk["bula"].removeprefix("bula_"))
        log.info("[%d/%d] %s: %d relações, %d descartes", i, len(chunks), chunk["id"],
                 len(limpa.relacoes), len(descartes))
        linhas.append({"chunk_id": chunk["id"], "bula": chunk["bula"], **limpa.model_dump(),
                       "descartes": descartes})
    return linhas, conta


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--bula", action="append", help="id do medicamento (ex.: cozaar)")
    p.add_argument("--bulas", type=int, help="só as N primeiras bulas (piloto)")
    p.add_argument("--max-chamadas", type=int, help="teto de chamadas ao LLM nesta rodada")
    p.add_argument("--pausa", type=float, default=0.0, help="segundos entre chamadas")
    p.add_argument("--modelo", default=config.LLM_MODEL, help="modelo só da extração")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    for ruido in ("google_genai", "httpx"):  # "AFC is enabled..." e uma linha por request
        logging.getLogger(ruido).setLevel(logging.WARNING)

    chunks = [json.loads(linha) for linha in (PROCESSADOS / "chunks.jsonl").open()]
    bulas = list(dict.fromkeys(c["bula"] for c in chunks))
    if a.bula:
        bulas = [f"bula_{b}" for b in a.bula]
    if a.bulas:
        bulas = bulas[: a.bulas]
    chunks = [c for c in chunks if c["bula"] in set(bulas)]

    # Retry fica aqui (ESPERAS_S), não no cliente: o retry interno travou minutos num 503.
    # Ollama ignora timeout/max_retries; o num_ctx padrão (4096) corta prompt + saída longa.
    extra = {"num_ctx": 8192} if config.LLM_PROVIDER == "ollama" else {}
    llm = config.get_llm(a.modelo, temperature=0, max_retries=0, timeout=120, **extra)
    linhas, conta = rodar(chunks, llm, a.modelo, a.max_chamadas, a.pausa)
    with SAIDA.open("w") as f:
        f.writelines(json.dumps(linha, ensure_ascii=False) + "\n" for linha in linhas)
    n_rel = sum(len(linha["relacoes"]) for linha in linhas)
    n_desc = sum(len(linha["descartes"]) for linha in linhas)
    print(f"{len(bulas)} bulas, {len(chunks)} chunks: {conta}")
    print(f"{SAIDA.name}: {len(linhas)} chunks, {n_rel} relações, {n_desc} descartes")
    return 1 if conta["falhas"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
