// Schema do grafo (E1.3). Referência: docs/modelagem.md.
// Idempotente: pode rodar várias vezes.
// Community Edition não tem constraint de existência/tipo de propriedade;
// os campos de cada label estão documentados em docs/modelagem.md.

// Unicidade de id (também cria índice range em id)
CREATE CONSTRAINT medicamento_id IF NOT EXISTS FOR (n:Medicamento) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT principio_ativo_id IF NOT EXISTS FOR (n:PrincipioAtivo) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT classe_terapeutica_id IF NOT EXISTS FOR (n:ClasseTerapeutica) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT condicao_id IF NOT EXISTS FOR (n:Condicao) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT efeito_adverso_id IF NOT EXISTS FOR (n:EfeitoAdverso) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT fabricante_id IF NOT EXISTS FOR (n:Fabricante) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT populacao_id IF NOT EXISTS FOR (n:Populacao) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT bula_id IF NOT EXISTS FOR (n:Bula) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT secao_id IF NOT EXISTS FOR (n:Secao) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.id IS UNIQUE;

// Range
CREATE INDEX secao_tipo IF NOT EXISTS FOR (n:Secao) ON (n.tipo);

// Fulltext
CREATE FULLTEXT INDEX entidade_nomes IF NOT EXISTS FOR (n:Entidade) ON EACH [n.nome, n.sinonimos];
CREATE FULLTEXT INDEX chunk_texto IF NOT EXISTS FOR (n:Chunk) ON EACH [n.texto];

// Vector: bge-m3, 1024 dimensões
CREATE VECTOR INDEX entidade_embedding IF NOT EXISTS FOR (n:Entidade) ON n.embedding_nome
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS FOR (n:Chunk) ON n.embedding
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
