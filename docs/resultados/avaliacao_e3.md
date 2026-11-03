# Avaliação da extração contra o gold (E3.5)

Chunks avaliados: 103

## Geral
| | TP | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|
| relações (estrito) | 428 | 223 | 317 | 0.657 | 0.574 | 0.613 |
| entidades (estrito) | 524 | 222 | 306 | 0.702 | 0.631 | 0.665 |
| relações (normalizado) | 455 | 193 | 287 | 0.702 | 0.613 | 0.655 |
| entidades (normalizado) | 562 | 181 | 263 | 0.756 | 0.681 | 0.717 |

## Relações por tipo (normalizado)
| | TP | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|
| CONTEM | 0 | 1 | 1 | 0.000 | 0.000 | 0.000 |
| CONTRAINDICADO_EM | 46 | 40 | 17 | 0.535 | 0.730 | 0.617 |
| INDICADO_PARA | 29 | 18 | 8 | 0.617 | 0.784 | 0.690 |
| INTERAGE_COM | 57 | 47 | 147 | 0.548 | 0.279 | 0.370 |
| PERTENCE_A | 5 | 10 | 31 | 0.333 | 0.139 | 0.196 |
| PODE_CAUSAR | 318 | 77 | 83 | 0.805 | 0.793 | 0.799 |

## Relações por bula (normalizado)
| | TP | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|
| bula_advil | 145 | 47 | 52 | 0.755 | 0.736 | 0.746 |
| bula_aspirina | 53 | 23 | 33 | 0.697 | 0.616 | 0.654 |
| bula_cozaar | 60 | 57 | 45 | 0.513 | 0.571 | 0.541 |
| bula_marevan | 88 | 17 | 86 | 0.838 | 0.506 | 0.631 |
| bula_renitec | 109 | 49 | 71 | 0.690 | 0.606 | 0.645 |
