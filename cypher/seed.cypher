// Grafo semente (E1.4): 5 bulas do profissional, Bulário Eletrônico da ANVISA (data/raw/).
// Fatos e textos tirados das bulas; trechos literais, com cortes marcados por (...).
// Idempotente: só MERGE. Rodar depois de cypher/schema.cypher.
// Gravidade das interações: as bulas não classificam, por isso 'desconhecida'.
// PODE_CAUSAR.frequencia: maior frequência citada na bula; 'desconhecida' quando a bula não quantifica.

// ---------- Entidades ----------

UNWIND [
  {id: 'cozaar',   nome: 'Cozaar',   reg: '1.0029.0007'},
  {id: 'renitec',  nome: 'Renitec',  reg: '1.0029.0031'},
  {id: 'marevan',  nome: 'Marevan',  reg: '1.0390.0147'},
  {id: 'advil',    nome: 'Advil',    reg: '1.9290.0005'},
  {id: 'aspirina', nome: 'Aspirina', reg: '1.7056.0020'}
] AS e
MERGE (n:Medicamento {id: e.id})
SET n:Entidade, n.nome = e.nome, n.sinonimos = [], n.registro_anvisa = e.reg, n.generico = false;

UNWIND [
  {id: 'losartana',              nome: 'Losartana',              sin: ['losartana potássica']},
  {id: 'enalapril',              nome: 'Enalapril',              sin: ['maleato de enalapril']},
  {id: 'varfarina',              nome: 'Varfarina',              sin: ['varfarina sódica']},
  {id: 'ibuprofeno',             nome: 'Ibuprofeno',             sin: []},
  {id: 'acido_acetilsalicilico', nome: 'Ácido acetilsalicílico', sin: ['AAS']}
] AS e
MERGE (n:PrincipioAtivo {id: e.id})
SET n:Entidade, n.nome = e.nome, n.sinonimos = e.sin;

UNWIND [
  {id: 'bra',               nome: 'Antagonista do receptor da angiotensina II', sin: ['BRA', 'ARA II', 'antagonistas de receptores da angiotensina II']},
  {id: 'ieca',              nome: 'Inibidor da ECA',               sin: ['IECA', 'inibidores da enzima conversora de angiotensina']},
  {id: 'anti_hipertensivo', nome: 'Anti-hipertensivo',             sin: ['agentes anti-hipertensivos']},
  {id: 'anticoagulante',    nome: 'Anticoagulante',                sin: ['anticoagulantes orais']},
  {id: 'aine',              nome: 'Anti-inflamatório não esteroide', sin: ['AINE', 'AINEs', 'anti-inflamatórios não esteroides', 'analgésicos anti-inflamatórios']},
  {id: 'salicilato',        nome: 'Salicilato',                    sin: ['salicilatos']}
] AS e
MERGE (n:ClasseTerapeutica {id: e.id})
SET n:Entidade, n.nome = e.nome, n.sinonimos = e.sin;

UNWIND [
  {id: 'hipertensao',            nome: 'Hipertensão',             sin: ['pressão alta', 'hipertensão essencial']},
  {id: 'insuficiencia_cardiaca', nome: 'Insuficiência cardíaca',  sin: []},
  {id: 'tromboembolismo',        nome: 'Tromboembolismo',         sin: ['tromboembolismo venoso', 'embolismo sistêmico']},
  {id: 'febre',                  nome: 'Febre',                   sin: []},
  {id: 'cefaleia',               nome: 'Cefaleia',                sin: ['dor de cabeça']},
  {id: 'dor_muscular',           nome: 'Dor muscular',            sin: ['mialgia']},
  {id: 'dismenorreia',           nome: 'Dismenorreia',            sin: ['cólica menstrual']},
  {id: 'insuficiencia_hepatica', nome: 'Insuficiência hepática',  sin: ['doença hepática grave']},
  {id: 'ulcera_peptica',         nome: 'Úlcera péptica',          sin: ['úlcera gastrintestinal', 'doença ulcerativa do trato gastrointestinal']},
  {id: 'hemorragia',             nome: 'Hemorragia',              sin: ['sangramento']},
  {id: 'hemofilia',              nome: 'Hemofilia',               sin: []},
  {id: 'dengue',                 nome: 'Dengue',                  sin: []},
  {id: 'angioedema_hereditario', nome: 'Angioedema hereditário',  sin: ['angioedema idiopático']}
] AS e
MERGE (n:Condicao {id: e.id})
SET n:Entidade, n.nome = e.nome, n.sinonimos = e.sin;

UNWIND [
  {id: 'tontura',                   nome: 'Tontura',                   sin: []},
  {id: 'vertigem',                  nome: 'Vertigem',                  sin: []},
  {id: 'cefaleia',                  nome: 'Cefaleia',                  sin: ['dor de cabeça']},
  {id: 'fadiga',                    nome: 'Fadiga',                    sin: []},
  {id: 'astenia',                   nome: 'Astenia',                   sin: ['fraqueza']},
  {id: 'tosse',                     nome: 'Tosse',                     sin: []},
  {id: 'hipercalemia',              nome: 'Hipercalemia',              sin: ['potássio alto']},
  {id: 'hipotensao',                nome: 'Hipotensão',                sin: ['pressão baixa', 'hipotensão ortostática']},
  {id: 'angioedema',                nome: 'Angioedema',                sin: ['edema angioneurótico']},
  {id: 'alopecia',                  nome: 'Alopecia',                  sin: ['queda de cabelo']},
  {id: 'hemorragia',                nome: 'Hemorragia',                sin: ['sangramento']},
  {id: 'nausea',                    nome: 'Náusea',                    sin: ['enjoo']},
  {id: 'dispepsia',                 nome: 'Dispepsia',                 sin: ['má digestão']},
  {id: 'diarreia',                  nome: 'Diarreia',                  sin: []},
  {id: 'zumbido',                   nome: 'Zumbido',                   sin: ['tinido', 'tinitos']},
  {id: 'urticaria',                 nome: 'Urticária',                 sin: []},
  {id: 'ulcera_gastrointestinal',   nome: 'Úlcera gastrointestinal',   sin: ['úlcera gastrintestinal']},
  {id: 'hemorragia_gastrointestinal', nome: 'Hemorragia gastrointestinal', sin: ['sangramento gastrintestinal']}
] AS e
MERGE (n:EfeitoAdverso {id: e.id})
SET n:Entidade, n.nome = e.nome, n.sinonimos = e.sin;

UNWIND [
  {id: 'organon',     nome: 'Organon Farmacêutica Ltda.'},
  {id: 'farmoquimica', nome: 'Farmoquímica S/A'},
  {id: 'pf_consumer', nome: 'PF Consumer Healthcare Brazil Importadora e Distribuidora de Medicamentos Ltda.'},
  {id: 'bayer',       nome: 'Bayer S.A.'}
] AS e
MERGE (n:Fabricante {id: e.id})
SET n:Entidade, n.nome = e.nome, n.sinonimos = [];

UNWIND [
  {id: 'gestante',   nome: 'Gestante',   sin: ['gravidez', 'grávida', 'gestação']},
  {id: 'lactante',   nome: 'Lactante',   sin: ['amamentação', 'lactação']},
  {id: 'pediatrico', nome: 'Pediátrico', sin: ['crianças', 'menores de 12 anos']},
  {id: 'idoso',      nome: 'Idoso',      sin: ['idosos']}
] AS e
MERGE (n:Populacao {id: e.id})
SET n:Entidade, n.nome = e.nome, n.sinonimos = e.sin;

// ---------- Bulas, seções e chunks ----------

UNWIND [
  {m: 'cozaar', s: 'indicacoes', o: 0, t: 'COZAAR® é indicado para o tratamento da hipertensão. COZAAR® é também indicado para o tratamento da insuficiência cardíaca, quando o tratamento com um inibidor da ECA não é mais considerado adequado.'},
  {m: 'cozaar', s: 'contraindicacoes', o: 0, t: 'COZAAR® não deve ser administrado durante o segundo ou o terceiro trimestre de gestação (veja o item 5. ADVERTÊNCIAS E PRECAUÇÕES – Uso na gravidez e amamentação). COZAAR® é contraindicado para pacientes com insuficiência hepática grave.'},
  {m: 'cozaar', s: 'interacoes', o: 0, t: 'Os fármacos anti-inflamatórios não esteroides (AINEs), incluindo os inibidores seletivos da cicloxigenase-2 (inibidores da COX-2), podem reduzir o efeito de diuréticos e outros medicamentos anti-hipertensivos. Por isso, o efeito anti-hipertensivo de antagonistas de receptores da angiotensina II ou inibidores da ECA pode ser atenuado pelos AINEs, incluindo os inibidores seletivos da COX-2.'},
  {m: 'cozaar', s: 'reacoes_adversas', o: 0, t: 'Tabela 1 (resumo): Tontura: comum. Vertigem: comum. Cefaleia: incomum. Hipotensão (ortostática): incomum a comum. Tosse: incomum. Astenia: incomum a comum. Fadiga: incomum a comum. Hipercalemia: comum. Reações de hipersensibilidade, reações anafiláticas, angioedema e vasculite: raro.'},

  {m: 'renitec', s: 'indicacoes', o: 0, t: 'RENITEC® é indicado para o tratamento de todos os graus de hipertensão essencial, tratamento da hipertensão renovascular e todos os graus de insuficiência cardíaca.'},
  {m: 'renitec', s: 'contraindicacoes', o: 0, t: 'RENITEC® é contraindicado para pacientes com hipersensibilidade a qualquer um de seus componentes, pacientes com histórico de edema angioneurótico relacionado a utilização de inibidores da enzima conversora de angiotensina e pacientes com angioedema hereditário ou idiopático.'},
  {m: 'renitec', s: 'advertencias', o: 0, t: 'Gravidez e amamentação: categoria de risco D. O uso de RENITEC® durante a gravidez não é recomendado. O tratamento com RENITEC® deve ser suspenso o mais rápido possível depois da confirmação de gravidez, a menos que seja considerado vital para a mãe.'},
  {m: 'renitec', s: 'interacoes', o: 0, t: 'Agentes anti-inflamatórios não esteroides, incluindo os inibidores seletivos da ciclooxigenase-2 (inibidores da COX-2), podem reduzir o efeito de diuréticos e de outros agentes anti-hipertensivos. Portanto, os efeitos anti-hipertensivos dos antagonistas dos receptores da angiotensina II ou dos inibidores da ECA podem ser atenuados pelos anti-inflamatórios não esteroides, incluindo os inibidores seletivos da COX-2.'},
  {m: 'renitec', s: 'reacoes_adversas', o: 0, t: 'As seguintes reações adversas foram associadas ao uso de RENITEC®: tontura e cefaleia foram as reações mais comumente relatadas; fadiga e astenia foram relatadas por 2% a 3% dos pacientes. Outras reações adversas ocorreram em menos de 2% dos pacientes e incluíram hipotensão, hipotensão ortostática, síncope, náuseas, diarreia, cãibras musculares, erupções cutâneas e tosse.'},
  {m: 'renitec', s: 'reacoes_adversas', o: 1, t: 'Hipersensibilidade/edema angioneurótico: edema angioneurótico de face, lábios, língua, glote e/ou laringe e extremidades foi relatado raramente. (...) Reações adversas que ocorreram muito raramente em estudos clínicos controlados ou após a comercialização incluem: (...) Pele: diaforese, eritema polimorfo, dermatite esfoliativa, síndrome de Stevens-Johnson, necrólise epidérmica tóxica, pênfigo, prurido, urticária, alopecia. (...) Ocorreram hipercalemia e hiponatremia.'},

  {m: 'marevan', s: 'indicacoes', o: 0, t: 'Marevan® é indicado para a prevenção primária e secundária do tromboembolismo venoso, na prevenção do embolismo sistêmico em pacientes com prótese de válvulas cardíacas ou fibrilação atrial e na prevenção do acidente vascular cerebral, do infarto agudo do miocárdio e da recorrência do infarto.'},
  {m: 'marevan', s: 'contraindicacoes', o: 0, t: 'Gravidez, especialmente durante o primeiro trimestre, devido à possibilidade de má-formação fetal. A administração a gestantes em estágios mais avançados está associada à hemorragia fetal e aumento na taxa de aborto. (...) Doenças hepáticas ou renais graves. Hemorragias. (...) Hemofilia. Doença ulcerativa ativa do trato gastrointestinal.'},
  {m: 'marevan', s: 'interacoes', o: 0, t: 'A atividade da varfarina pode ser potencializada por (...) salicilatos, (...) diflunisal, flurbiprofeno, indometacina, ácido mefenâmico, piroxicam, sulindaco e, possivelmente, outros analgésicos anti-inflamatórios (...). Em caso de suspeita de dengue, ou quando associado a outros medicamentos que aumentem o efeito hemorrágico, a prescrição deste medicamento ou a manutenção do tratamento com ele deve ser reavaliada, devido a seu potencial hemorrágico.'},
  {m: 'marevan', s: 'reacoes_adversas', o: 0, t: 'Hemorragia de menor ou maior intensidade pode ocorrer durante a terapia com Marevan®, em qualquer tecido ou órgão, manifestando-se como sangramento externo ou interno. (...) Desordens do sistema nervoso: tonturas, cefaleias, hemorragia intracraniana. (...) Desordens do tecido subcutâneo e pele: alopecia, dermatite, dermatite bolhosa, petéquias, prurido, erupção cutânea, necrose da pele, urticária.'},

  {m: 'advil', s: 'indicacoes', o: 0, t: 'Advil® 400 mg cápsulas moles está indicado no alívio temporário da febre e de dores de leve a moderada intensidade como cefaleia tensional, lombalgia, dor muscular, enxaqueca, dismenorreia, de gripes e resfriados comuns, de artrite e dor de dente.'},
  {m: 'advil', s: 'contraindicacoes', o: 0, t: 'Este medicamento é contraindicado (...) durante os últimos 3 meses de gravidez; em pacientes com úlcera péptica ativa ou prévia; (...) em pacientes com insuficiência hepática. (...) Este medicamento é contraindicado para menores de 12 anos. Este medicamento é contraindicado em caso de suspeita de dengue, pois pode aumentar o risco de sangramentos.'},
  {m: 'advil', s: 'interacoes', o: 0, t: 'O ibuprofeno não deve ser usado em combinação com outros medicamentos anti-inflamatórios não esteróides (AINEs), incluindo ácido acetilsalicílico e inibidores específicos da ciclo-oxigenase-2, pois podem aumentar o risco de efeitos adversos. O ibuprofeno pode inibir o efeito antiplaquetário do ácido acetilsalicílico.'},
  {m: 'advil', s: 'interacoes', o: 1, t: 'Anticoagulantes: os AINEs podem potencializar os efeitos dos anticoagulantes, como a varfarina. (...) Diuréticos e anti-hipertensivos: como outros AINEs, o uso concomitante de ibuprofeno com diuréticos ou agentes anti-hipertensivos (por exemplo, betabloqueadores, inibidores da enzima de conversão da angiotensina (ECA)) pode causar uma diminuição no seu efeito anti-hipertensivo.'},
  {m: 'advil', s: 'reacoes_adversas', o: 0, t: 'Reação comum (> 1/100 e ≤ 1/10): Náusea, dispepsia, diarreia, vómitos, dor de cabeça, sonolência, tontura. Reação incomum (> 1/1.000 e ≤ 1/100): Dor abdominal, prisão de ventre, flatulência, erupções cutâneas, reações de hipersensibilidade incluindo urticária e prurido, zumbido. Reação rara (> 1/10.000 e ≤ 1.000): (...) úlcera gastrointestinal, gastrite (...). Reação muito rara (≤ 1/10.000): Perfuração ou hemorragia gastrointestinal, por vezes fatal, particularmente nos idosos.'},

  {m: 'aspirina', s: 'indicacoes', o: 0, t: 'Para o alívio sintomático da cefaleia, odontalgia, dor de garganta relacionada a resfriados, dismenorreia, mialgia ou artralgia, lombalgia e dor artrítica de pequena intensidade; no resfriado comum ou na gripe, para o alívio sintomático da dor e da febre.'},
  {m: 'aspirina', s: 'contraindicacoes', o: 0, t: 'Úlceras gastrintestinais agudas; diátese hemorrágica; insuficiência renal grave; insuficiência hepática grave; insuficiência cardíaca grave; (...) último trimestre de gravidez. (...) Este medicamento é contraindicado em caso de suspeita de dengue, pois pode aumentar o risco de sangramentos.'},
  {m: 'aspirina', s: 'interacoes', o: 0, t: 'Anticoagulantes, trombolíticos/ outros inibidores da agregação plaquetária/ homeostasia: aumento do risco de sangramento. Outros anti-inflamatórios não-esteroides com salicilatos em altas doses: aumento do risco de úlceras e sangramento gastrintestinal devido ao efeito sinérgico. (...) Inibidores da enzima conversora de angiotensina (ECA) em associação com o ácido acetilsalicílico em altas doses: diminuição da filtração glomerular por inibição das prostaglandinas vasodilatadoras. Além disso, diminuição do efeito anti-hipertensivo.'},
  {m: 'aspirina', s: 'reacoes_adversas', o: 0, t: 'Distúrbios do trato gastrintestinal superior e inferior como sinais e sintomas de dispepsia, dor gastrintestinal e abdominal, raramente inflamação gastrintestinal, úlcera gastrintestinal, levando potencialmente, mas muito raramente, a úlcera gastrintestinal com hemorragia e perfuração. (...) Devido a seu efeito inibitório sobre a agregação plaquetária, o ácido acetilsalicílico pode estar associado com o aumento do risco de sangramento. (...) rash cutâneo, urticária, edema, prurido (...).'}
] AS c
MATCH (m:Medicamento {id: c.m})
MERGE (b:Bula {id: 'bula_' + c.m})
SET b.tipo = 'profissional',
    b.arquivo = 'data/raw/bula_' + c.m + '.pdf',
    b.url = 'https://consultas.anvisa.gov.br/#/bulario/'
MERGE (b)-[:DESCREVE]->(m)
MERGE (s:Secao {id: b.id + '_' + c.s})
SET s.tipo = c.s
MERGE (b)-[:TEM_SECAO]->(s)
MERGE (ch:Chunk {id: s.id + '_' + c.o})
SET ch.texto = c.t, ch.ordem = c.o
MERGE (s)-[:TEM_CHUNK]->(ch);

MATCH (b:Bula {id: 'bula_marevan'}) SET b.data_publicacao = date('2025-10-22');

// ---------- Relações de domínio ----------
// fonte_chunk_id null = fato da capa/composição da bula, sem chunk de texto.

UNWIND [
  {m: 'cozaar',   p: 'losartana',              dose: '50 mg; 100 mg'},
  {m: 'renitec',  p: 'enalapril',              dose: '5 mg; 10 mg; 20 mg'},
  {m: 'marevan',  p: 'varfarina',              dose: '2,5 mg; 5 mg; 7,5 mg'},
  {m: 'advil',    p: 'ibuprofeno',             dose: '400 mg'},
  {m: 'aspirina', p: 'acido_acetilsalicilico', dose: '500 mg'}
] AS r
MATCH (a:Medicamento {id: r.m}), (b:PrincipioAtivo {id: r.p})
MERGE (a)-[x:CONTEM]->(b)
SET x.dose = r.dose, x.fonte_chunk_id = null, x.confianca = 1.0, x.metodo = 'manual';

UNWIND [
  {m: 'cozaar', f: 'organon'}, {m: 'renitec', f: 'organon'}, {m: 'marevan', f: 'farmoquimica'},
  {m: 'advil', f: 'pf_consumer'}, {m: 'aspirina', f: 'bayer'}
] AS r
MATCH (a:Medicamento {id: r.m}), (b:Fabricante {id: r.f})
MERGE (a)-[x:FABRICADO_POR]->(b)
SET x.fonte_chunk_id = null, x.confianca = 1.0, x.metodo = 'manual';

UNWIND [
  {p: 'losartana',              c: 'bra',               f: null},
  {p: 'losartana',              c: 'anti_hipertensivo', f: null},
  {p: 'enalapril',              c: 'ieca',              f: null},
  {p: 'enalapril',              c: 'anti_hipertensivo', f: null},
  {p: 'varfarina',              c: 'anticoagulante',    f: 'bula_advil_interacoes_1'},
  {p: 'ibuprofeno',             c: 'aine',              f: 'bula_advil_interacoes_0'},
  {p: 'acido_acetilsalicilico', c: 'aine',              f: 'bula_advil_interacoes_0'},
  {p: 'acido_acetilsalicilico', c: 'salicilato',        f: null}
] AS r
MATCH (a:PrincipioAtivo {id: r.p}), (b:ClasseTerapeutica {id: r.c})
MERGE (a)-[x:PERTENCE_A]->(b)
SET x.fonte_chunk_id = r.f, x.confianca = 1.0, x.metodo = 'manual';

UNWIND [
  {m: 'cozaar',   c: 'hipertensao',            f: 'bula_cozaar_indicacoes_0'},
  {m: 'cozaar',   c: 'insuficiencia_cardiaca', f: 'bula_cozaar_indicacoes_0'},
  {m: 'renitec',  c: 'hipertensao',            f: 'bula_renitec_indicacoes_0'},
  {m: 'renitec',  c: 'insuficiencia_cardiaca', f: 'bula_renitec_indicacoes_0'},
  {m: 'marevan',  c: 'tromboembolismo',        f: 'bula_marevan_indicacoes_0'},
  {m: 'advil',    c: 'febre',                  f: 'bula_advil_indicacoes_0'},
  {m: 'advil',    c: 'cefaleia',               f: 'bula_advil_indicacoes_0'},
  {m: 'advil',    c: 'dor_muscular',           f: 'bula_advil_indicacoes_0'},
  {m: 'advil',    c: 'dismenorreia',           f: 'bula_advil_indicacoes_0'},
  {m: 'aspirina', c: 'febre',                  f: 'bula_aspirina_indicacoes_0'},
  {m: 'aspirina', c: 'cefaleia',               f: 'bula_aspirina_indicacoes_0'},
  {m: 'aspirina', c: 'dor_muscular',           f: 'bula_aspirina_indicacoes_0'},
  {m: 'aspirina', c: 'dismenorreia',           f: 'bula_aspirina_indicacoes_0'}
] AS r
MATCH (a:Medicamento {id: r.m}), (b:Condicao {id: r.c})
MERGE (a)-[x:INDICADO_PARA]->(b)
SET x.fonte_chunk_id = r.f, x.confianca = 1.0, x.metodo = 'manual';

UNWIND [
  {m: 'cozaar',   c: 'gestante',               f: 'bula_cozaar_contraindicacoes_0'},
  {m: 'cozaar',   c: 'insuficiencia_hepatica', f: 'bula_cozaar_contraindicacoes_0'},
  {m: 'renitec',  c: 'angioedema_hereditario', f: 'bula_renitec_contraindicacoes_0'},
  {m: 'marevan',  c: 'gestante',               f: 'bula_marevan_contraindicacoes_0'},
  {m: 'marevan',  c: 'insuficiencia_hepatica', f: 'bula_marevan_contraindicacoes_0'},
  {m: 'marevan',  c: 'hemorragia',             f: 'bula_marevan_contraindicacoes_0'},
  {m: 'marevan',  c: 'hemofilia',              f: 'bula_marevan_contraindicacoes_0'},
  {m: 'marevan',  c: 'ulcera_peptica',         f: 'bula_marevan_contraindicacoes_0'},
  {m: 'advil',    c: 'gestante',               f: 'bula_advil_contraindicacoes_0'},
  {m: 'advil',    c: 'pediatrico',             f: 'bula_advil_contraindicacoes_0'},
  {m: 'advil',    c: 'ulcera_peptica',         f: 'bula_advil_contraindicacoes_0'},
  {m: 'advil',    c: 'insuficiencia_hepatica', f: 'bula_advil_contraindicacoes_0'},
  {m: 'advil',    c: 'dengue',                 f: 'bula_advil_contraindicacoes_0'},
  {m: 'aspirina', c: 'gestante',               f: 'bula_aspirina_contraindicacoes_0'},
  {m: 'aspirina', c: 'ulcera_peptica',         f: 'bula_aspirina_contraindicacoes_0'},
  {m: 'aspirina', c: 'insuficiencia_hepatica', f: 'bula_aspirina_contraindicacoes_0'},
  {m: 'aspirina', c: 'dengue',                 f: 'bula_aspirina_contraindicacoes_0'}
] AS r
MATCH (a:Medicamento {id: r.m})
MATCH (b:Entidade {id: r.c}) WHERE b:Condicao OR b:Populacao
MERGE (a)-[x:CONTRAINDICADO_EM]->(b)
SET x.fonte_chunk_id = r.f, x.confianca = 1.0, x.metodo = 'manual';

UNWIND [
  {m: 'cozaar',   e: 'tontura',      q: 'comum',       f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'vertigem',     q: 'comum',       f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'cefaleia',     q: 'incomum',     f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'hipotensao',   q: 'comum',       f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'tosse',        q: 'incomum',     f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'astenia',      q: 'comum',       f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'fadiga',       q: 'comum',       f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'hipercalemia', q: 'comum',       f: 'bula_cozaar_reacoes_adversas_0'},
  {m: 'cozaar',   e: 'angioedema',   q: 'rara',        f: 'bula_cozaar_reacoes_adversas_0'},

  {m: 'renitec',  e: 'tontura',      q: 'desconhecida', f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'cefaleia',     q: 'desconhecida', f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'fadiga',       q: 'comum',        f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'astenia',      q: 'comum',        f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'hipotensao',   q: 'desconhecida', f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'nausea',       q: 'desconhecida', f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'diarreia',     q: 'desconhecida', f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'tosse',        q: 'desconhecida', f: 'bula_renitec_reacoes_adversas_0'},
  {m: 'renitec',  e: 'angioedema',   q: 'rara',         f: 'bula_renitec_reacoes_adversas_1'},
  {m: 'renitec',  e: 'alopecia',     q: 'muito_rara',   f: 'bula_renitec_reacoes_adversas_1'},
  {m: 'renitec',  e: 'urticaria',    q: 'muito_rara',   f: 'bula_renitec_reacoes_adversas_1'},
  {m: 'renitec',  e: 'hipercalemia', q: 'desconhecida', f: 'bula_renitec_reacoes_adversas_1'},

  {m: 'marevan',  e: 'hemorragia',   q: 'desconhecida', f: 'bula_marevan_reacoes_adversas_0'},
  {m: 'marevan',  e: 'tontura',      q: 'desconhecida', f: 'bula_marevan_reacoes_adversas_0'},
  {m: 'marevan',  e: 'cefaleia',     q: 'desconhecida', f: 'bula_marevan_reacoes_adversas_0'},
  {m: 'marevan',  e: 'alopecia',     q: 'desconhecida', f: 'bula_marevan_reacoes_adversas_0'},
  {m: 'marevan',  e: 'urticaria',    q: 'desconhecida', f: 'bula_marevan_reacoes_adversas_0'},

  {m: 'advil',    e: 'nausea',       q: 'comum',        f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'dispepsia',    q: 'comum',        f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'diarreia',     q: 'comum',        f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'cefaleia',     q: 'comum',        f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'tontura',      q: 'comum',        f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'urticaria',    q: 'incomum',      f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'zumbido',      q: 'incomum',      f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'ulcera_gastrointestinal',     q: 'rara',       f: 'bula_advil_reacoes_adversas_0'},
  {m: 'advil',    e: 'hemorragia_gastrointestinal', q: 'muito_rara', f: 'bula_advil_reacoes_adversas_0'},

  {m: 'aspirina', e: 'dispepsia',    q: 'desconhecida', f: 'bula_aspirina_reacoes_adversas_0'},
  {m: 'aspirina', e: 'ulcera_gastrointestinal',     q: 'rara',       f: 'bula_aspirina_reacoes_adversas_0'},
  {m: 'aspirina', e: 'hemorragia_gastrointestinal', q: 'muito_rara', f: 'bula_aspirina_reacoes_adversas_0'},
  {m: 'aspirina', e: 'hemorragia',   q: 'desconhecida', f: 'bula_aspirina_reacoes_adversas_0'},
  {m: 'aspirina', e: 'urticaria',    q: 'desconhecida', f: 'bula_aspirina_reacoes_adversas_0'}
] AS r
MATCH (a:Medicamento {id: r.m}), (b:EfeitoAdverso {id: r.e})
MERGE (a)-[x:PODE_CAUSAR]->(b)
SET x.frequencia = r.q, x.fonte_chunk_id = r.f, x.confianca = 1.0, x.metodo = 'manual';

UNWIND [
  {de: 'losartana',              para: 'aine',                   efeito: 'AINEs podem atenuar o efeito anti-hipertensivo', f: 'bula_cozaar_interacoes_0'},
  {de: 'enalapril',              para: 'aine',                   efeito: 'AINEs podem atenuar o efeito anti-hipertensivo', f: 'bula_renitec_interacoes_0'},
  {de: 'varfarina',              para: 'aine',                   efeito: 'potencializa a atividade anticoagulante da varfarina', f: 'bula_marevan_interacoes_0'},
  {de: 'varfarina',              para: 'salicilato',             efeito: 'potencializa a atividade anticoagulante da varfarina', f: 'bula_marevan_interacoes_0'},
  {de: 'ibuprofeno',             para: 'acido_acetilsalicilico', efeito: 'ibuprofeno pode inibir o efeito antiplaquetário do ácido acetilsalicílico; aumenta o risco de efeitos adversos', f: 'bula_advil_interacoes_0'},
  {de: 'ibuprofeno',             para: 'anticoagulante',         efeito: 'AINEs podem potencializar os efeitos dos anticoagulantes', f: 'bula_advil_interacoes_1'},
  {de: 'ibuprofeno',             para: 'anti_hipertensivo',      efeito: 'diminuição do efeito anti-hipertensivo', f: 'bula_advil_interacoes_1'},
  {de: 'acido_acetilsalicilico', para: 'anticoagulante',         efeito: 'aumento do risco de sangramento', f: 'bula_aspirina_interacoes_0'},
  {de: 'acido_acetilsalicilico', para: 'aine',                   efeito: 'em altas doses, aumento do risco de úlceras e sangramento gastrintestinal', f: 'bula_aspirina_interacoes_0'},
  {de: 'acido_acetilsalicilico', para: 'ieca',                   efeito: 'em altas doses, diminuição da filtração glomerular e do efeito anti-hipertensivo', f: 'bula_aspirina_interacoes_0'}
] AS r
MATCH (a:PrincipioAtivo {id: r.de})
MATCH (b:Entidade {id: r.para}) WHERE b:PrincipioAtivo OR b:ClasseTerapeutica
MERGE (a)-[x:INTERAGE_COM]->(b)
SET x.gravidade = 'desconhecida', x.efeito = r.efeito,
    x.fonte_chunk_id = r.f, x.confianca = 1.0, x.metodo = 'manual';

// ---------- Proveniência: chunk menciona as pontas de cada relação que sustenta ----------

MATCH (a)-[r]->(b) WHERE r.fonte_chunk_id IS NOT NULL
MATCH (c:Chunk {id: r.fonte_chunk_id})
MERGE (c)-[:MENCIONA]->(a)
MERGE (c)-[:MENCIONA]->(b);
