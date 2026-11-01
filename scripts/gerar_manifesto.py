"""Gera data/raw/manifesto.jsonl a partir do texto das bulas (E2.2).

Uso: uv run python scripts/gerar_manifesto.py
Requer o binário `pdftotext` (poppler).

O número do expediente não aparece no PDF (só na página do Bulário), então
fica null, exceto quando já estava preenchido no manifesto anterior.
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
MANIFESTO = RAW / "manifesto.jsonl"

DATA = r"\d{2}/\d{2}/\d{4}"
RE_APROVACAO = re.compile(rf"aprovada pela anvisa em\s*({DATA})", re.I)
RE_REGISTRO = re.compile(r"\b1\.\d{4}\.\d{4}(?:\.\d{3}-?\d)?")
RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_REGISTRADO = re.compile(r"registrad[oa][^:\n]{0,30}por\s*:?", re.I)
RE_EMPRESA = re.compile(r"(.*?\b(?:Ltda|LTDA|S\.\s?A|S/A)\b\.?)")
RE_HISTORICO =re.compile(r"hist.rico de altera", re.I)
# Seções que só existem na bula do profissional (RDC 47/2009).
RE_PROFISSIONAL = re.compile(r"resultados de efic.cia|caracter.sticas farmacol.gicas", re.I)


def texto(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True
    ).stdout


def empresa_e_cnpj(txt: str) -> tuple[str | None, str | None]:
    """Empresa = 1ª linha após 'Registrado ... por:'; CNPJ = 1º CNPJ depois dela."""
    m = RE_REGISTRADO.search(txt)
    if not m:
        cnpj = RE_CNPJ.search(txt)
        return None, cnpj.group() if cnpj else None
    resto = txt[m.end():]
    # Descarta ruído de rodapé ("16", "- 8 de 9 -", "Internal", "VV-REG-...").
    linhas = [
        linha.strip() for linha in resto.splitlines()[:12]
        if re.search(r"[A-Za-zÀ-ú]{3}", linha) and not re.match(r"\s*(Internal|VV-)", linha)
    ]
    janela = " ".join(linhas[:4])
    sufixo = RE_EMPRESA.match(janela)
    nome = sufixo.group(1) if sufixo else (linhas[0] if linhas else None)
    cnpj = RE_CNPJ.search(resto)
    return nome, cnpj.group() if cnpj else None


def data_publicacao(txt: str) -> str | None:
    """Data de aprovação declarada na bula; senão, a data mais recente do histórico."""
    if m := RE_APROVACAO.search(txt):
        return m.group(1)
    h = RE_HISTORICO.search(txt)
    datas = []
    for d in re.findall(DATA, txt[h.start() if h else 0:]):
        try:
            datas.append(datetime.strptime(d, "%d/%m/%Y"))
        except ValueError:
            pass
    datas = [d for d in datas if 2000 <= d.year <= datetime.now().year]
    return max(datas).strftime("%d/%m/%Y") if datas else None


def extrair(pdf: Path) -> dict:
    txt = texto(pdf)
    empresa, cnpj = empresa_e_cnpj(txt)
    registro = RE_REGISTRO.search(txt)
    return {
        "arquivo": pdf.name,
        "medicamento": pdf.stem.removeprefix("bula_").upper(),
        "empresa": empresa,
        "cnpj": cnpj,
        "registro_ms": registro.group() if registro else None,
        "expediente": None,
        "data_publicacao": data_publicacao(txt),
        "tipo": "profissional" if RE_PROFISSIONAL.search(txt) else "paciente",
        "fonte": "Bulário Eletrônico ANVISA",
    }


def main() -> None:
    anteriores = {}
    if MANIFESTO.exists():
        for linha in MANIFESTO.read_text().splitlines():
            if linha.strip():
                e = json.loads(linha)
                anteriores[e["arquivo"]] = e
    linhas = []
    for pdf in sorted(RAW.glob("*.pdf"), key=lambda p: p.name.lower()):
        e = extrair(pdf)
        e["expediente"] = anteriores.get(pdf.name, {}).get("expediente")
        faltando = [k for k, v in e.items() if v is None and k != "expediente"]
        if faltando:
            print(f"{pdf.name}: sem {', '.join(faltando)}")
        linhas.append(json.dumps(e, ensure_ascii=False))
    MANIFESTO.write_text("\n".join(linhas) + "\n")
    print(f"{len(linhas)} bulas em {MANIFESTO}")


if __name__ == "__main__":
    main()
