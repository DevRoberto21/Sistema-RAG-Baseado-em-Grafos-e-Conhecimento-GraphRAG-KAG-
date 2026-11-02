"""Ingestão no Neo4j (E4.3, E4.4). Montagem das linhas sem banco; carga com a fixture db."""

from graphrag_bulas import ingestao as ig


def test_statements_ignora_comentario_e_ponto_e_virgula_dentro_de_string():
    texto = "// comentário; com ponto e vírgula\nCREATE (n {t: 'a; b'});\nMATCH (n) RETURN n;\n"
    assert ig.statements(texto) == ["CREATE (n {t: 'a; b'})", "MATCH (n) RETURN n"]


def test_statements_do_seed_e_do_schema():
    assert len(ig.statements((ig.CYPHER / "schema.cypher").read_text())) == 15
    assert len(ig.statements((ig.CYPHER / "seed.cypher").read_text())) == 17


MANIFESTO = [
    {
        "arquivo": "bula_cozaar.pdf",
        "medicamento": "COZAAR",
        "empresa": "Organon Farmacêutica Ltda.",
        "registro_ms": "1.0029.0007",
        "data_publicacao": "24/04/2025",
    },
    {
        "arquivo": "bula_Lipitor.pdf",
        "medicamento": "LIPITOR",
        "empresa": "Pfizer Brasil Ltda.",
        "registro_ms": "1.0216.0001",
        "data_publicacao": "01/01/2025",
    },
]


def test_linhas_bulas_filtra_escopo_e_resolve_fabricante():
    rows = ig.linhas_bulas(MANIFESTO, {"bula_cozaar"}, {"organon_farmaceutica_ltda": "organon"})
    assert rows == [
        {
            "bula": "bula_cozaar",
            "med": "cozaar",
            "nome": "Cozaar",
            "arquivo": "data/raw/bula_cozaar.pdf",
            "registro": "1.0029.0007",
            "data": "2025-04-24",
            "fab": "organon",
            "fab_nome": "Organon Farmacêutica Ltda.",
        }
    ]


def test_linhas_chunks_filtra_escopo():
    chunks = [
        {
            "id": "bula_cozaar_indicacoes_0",
            "bula": "bula_cozaar",
            "secao": "bula_cozaar_indicacoes",
            "tipo": "indicacoes",
            "ordem": 0,
            "texto": "t",
        },
        {
            "id": "bula_lipitor_indicacoes_0",
            "bula": "bula_lipitor",
            "secao": "bula_lipitor_indicacoes",
            "tipo": "indicacoes",
            "ordem": 0,
            "texto": "u",
        },
    ]
    assert [c["id"] for c in ig.linhas_chunks(chunks, {"bula_cozaar"})] == [
        "bula_cozaar_indicacoes_0"
    ]


def test_linhas_composicao_usa_nome_do_grafo_ou_id():
    rows = ig.linhas_composicao(
        [{"label": "PrincipioAtivo", "id": "losartana", "nome": "Losartana", "sinonimos": []}]
    )
    assert {"med": "cozaar", "pa": "losartana", "nome": "Losartana"} in rows
    assert {
        "med": "aspirina",
        "pa": "acido_acetilsalicilico",
        "nome": "Acido acetilsalicilico",
    } in rows


REL = {
    "rel": "INTERAGE_COM",
    "label_origem": "PrincipioAtivo",
    "origem": "losartana",
    "label_destino": "ClasseTerapeutica",
    "destino": "aine",
    "chunks": ["bula_cozaar_interacoes_0", "bula_cozaar_interacoes_1"],
}


def test_linhas_menciona_sem_repeticao():
    por_label = ig.linhas_menciona([REL, REL])
    assert por_label["PrincipioAtivo"] == [
        {"id": "losartana", "chunk": "bula_cozaar_interacoes_0"},
        {"id": "losartana", "chunk": "bula_cozaar_interacoes_1"},
    ]
    assert len(por_label["ClasseTerapeutica"]) == 2


def test_ler_grafo_separa_nos_e_relacoes(tmp_path):
    arq = tmp_path / "grafo.jsonl"
    arq.write_text('{"tipo": "no", "id": "a"}\n{"tipo": "rel", "rel": "X"}\n')
    nos, rels = ig.ler_grafo(arq)
    assert [n["id"] for n in nos] == ["a"] and [r["rel"] for r in rels] == ["X"]
