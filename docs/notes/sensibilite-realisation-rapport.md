# Sensibilité au profil de réalisation (FR-008a, SC-009)

Écart d(h) = ½ Σ |stratégie_variante - stratégie_défaut| : part de la stratégie
qui change d'action. Moyenne pondérée par la masse de chaque main au nœud ; maximum
et changements d'action majoritaire sur les mains qui atteignent le nœud à au moins
1%. Tout écart est relatif au modèle (préflop avec réalisation d'équité).

## 5bb

| Variante | Écart moyen | Nœud le plus touché (écart max) | Mains qui changent d'action majoritaire | EV racine BTN / SB / BB (défaut → variante) | NashConv |
|---|---|---|---|---|---|
| U+ | 0.00% | C (3%) | 0 | +0.289 → +0.289 / -0.035 → -0.035 / -0.254 → -0.254 | 0.002 % |
| U- | 0.00% | C-C-A-C (6%) | 2 | +0.289 → +0.289 / -0.035 → -0.035 / -0.254 → -0.254 | 0.002 % |
| E+ | 0.01% | F-C (39%) | 26 | +0.289 → +0.289 / -0.035 → -0.035 / -0.254 → -0.254 | 0.002 % |
| E- | 0.01% | C (44%) | 21 | +0.289 → +0.289 / -0.035 → -0.035 / -0.254 → -0.254 | 0.002 % |

### 5bb, U+ : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 59.1% | 0.00% | 0% |  |
| root | BTN | 100.0% | 0.00% | 0% |  |
| A-F | BB | 28.6% | 0.00% | 0% |  |
| F-A | BB | 41.8% | 0.00% | 0% |  |
| F-C | BB | 0.0% | 0.15% | 1% |  |

### 5bb, U- : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 59.1% | 0.00% | 0% |  |
| root | BTN | 100.0% | 0.00% | 0% |  |
| A-F | BB | 28.6% | 0.00% | 0% |  |
| F-A | BB | 41.8% | 0.00% | 0% |  |
| F-C | BB | 0.0% | 0.18% | 2% | 33 |

### 5bb, E+ : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 59.1% | 0.03% | 2% |  |
| root | BTN | 100.0% | 0.01% | 1% |  |
| A-F | BB | 28.6% | 0.00% | 0% |  |
| F-C | BB | 0.0% | 6.16% | 39% | Q3s Q2s J7s T9s J8o Q6o Q5o 55 44 33 22 |
| F-A | BB | 41.8% | 0.00% | 0% |  |

### 5bb, E- : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 59.1% | 0.03% | 3% |  |
| root | BTN | 100.0% | 0.00% | 0% |  |
| A-F | BB | 28.6% | 0.00% | 0% |  |
| F-A | BB | 41.8% | 0.00% | 0% |  |
| F-C | BB | 0.0% | 4.92% | 25% | T8s Q4o Q3o Q2o |

## 12bb

| Variante | Écart moyen | Nœud le plus touché (écart max) | Mains qui changent d'action majoritaire | EV racine BTN / SB / BB (défaut → variante) | NashConv |
|---|---|---|---|---|---|
| U+ | 0.44% | C-C-R4.0-F (85%) | 42 | +0.220 → +0.220 / -0.083 → -0.082 / -0.136 → -0.138 | 0.091 % |
| U- | 0.58% | C-C-R4.0-F (83%) | 59 | +0.220 → +0.220 / -0.083 → -0.084 / -0.136 → -0.135 | 0.098 % |
| E+ | 10.42% | C-C-R4.0-F (100%) | 494 | +0.220 → +0.224 / -0.083 → -0.103 / -0.136 → -0.121 | 0.097 % |
| E- | 5.27% | C-C-R4.0-C (100%) | 477 | +0.220 → +0.220 / -0.083 → -0.066 / -0.136 → -0.154 | 0.043 % |

### 12bb, U+ : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 68.1% | 0.91% | 22% | 95s |
| F-C | BB | 23.4% | 1.28% | 15% | AKo T5s 52s |
| root | BTN | 100.0% | 0.23% | 11% | T7s |
| F-C-R3.0 | SB | 4.3% | 0.94% | 12% |  |
| A | SB | 31.2% | 0.11% | 10% |  |

### 12bb, U- : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 68.1% | 1.18% | 24% | K7o |
| F-C | BB | 23.4% | 1.89% | 20% | 42s 32s |
| root | BTN | 100.0% | 0.29% | 11% | A2o |
| A | SB | 31.2% | 0.16% | 13% |  |
| F-C-R3.0 | SB | 4.3% | 1.11% | 20% | K9s |

### 12bb, E+ : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 68.1% | 20.51% | 99% | KK QJs QTs Q3s JTs J8s J6s J5s J3s J2s TT T5s T4s T3s T2s (+18) |
| root | BTN | 100.0% | 8.39% | 97% | AA AQs KK K8s K7s K6s QQ JJ KTo QTo K9o 97s 76s A3o A2o |
| F-C | BB | 23.4% | 26.93% | 98% | ATs A9s A8s A7s A6s A5s A4s A3s A2s K5s K4s K3s K2s QTs Q9s (+39) |
| F-C-R3.0 | SB | 4.3% | 13.63% | 97% | K9s K8s K7s K6s Q8s Q4s J8s J6s J5s J4s J3s JTo T5s T4s K9o (+2) |
| A-F | BB | 26.7% | 1.16% | 95% | K9s JTs KTo |

### 12bb, E- : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 68.1% | 12.84% | 98% | AKs AQs AJs ATs KQs KJs KTs K9s K8s Q9s Q4s J9s 95s 94s 93s (+13) |
| F-C | BB | 23.4% | 19.22% | 99% | AKs AQs AJs AKo KQs KJs KTs K6s AQo KQo QJs KJo JJ TT T6s (+24) |
| root | BTN | 100.0% | 0.94% | 41% | T7s |
| F-C-R3.0 | SB | 4.3% | 12.00% | 96% | A5s KTs Q8s Q3s Q2s J2s T3s T2s 99 88 K2o |
| F-C-A | SB | 6.2% | 1.91% | 53% | K8o |

## 20bb

| Variante | Écart moyen | Nœud le plus touché (écart max) | Mains qui changent d'action majoritaire | EV racine BTN / SB / BB (défaut → variante) | NashConv |
|---|---|---|---|---|---|
| U+ | 1.99% | C-C-R4.0-C-R12.0-A-F (90%) | 203 | +0.195 → +0.193 / -0.146 → -0.141 / -0.050 → -0.052 | 0.054 % |
| U- | 2.35% | R2.5-F (96%) | 219 | +0.195 → +0.199 / -0.146 → -0.150 / -0.050 → -0.049 | 0.052 % |
| E+ | 18.48% | C-C-R4.0-F-A (100%) | 1001 | +0.195 → +0.230 / -0.146 → -0.175 / -0.050 → -0.055 | 0.084 % |
| E- | 17.82% | C-R3.0-R9.0-F (100%) | 1150 | +0.195 → +0.164 / -0.146 → -0.088 / -0.050 → -0.076 | 0.087 % |

### 20bb, U+ : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 71.9% | 3.13% | 78% | A5s A2s KTs KTo T6s 84s 53s |
| root | BTN | 100.0% | 1.46% | 51% | A5s K6s QTs J9s 66 |
| F-C | BB | 36.3% | 3.21% | 48% | K2s QTs JTs A9o 65s 43s |
| R2.5-F | BB | 19.7% | 3.93% | 86% | Q8s 98s 55 T4o 84o 63o 33 52o |
| F-C-R3.0 | SB | 12.6% | 1.44% | 32% | QJo T5s 87o |

### 20bb, U- : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 71.9% | 4.55% | 53% | AQs AJs A4s K8s QTs T9o 92s 86o A4o 33 |
| F-C | BB | 36.3% | 3.77% | 55% | QTs Q8s JTs T9s 97s 93s 92s 83s 82s 53s 32s |
| root | BTN | 100.0% | 1.17% | 33% | AJo |
| R2.5-F | BB | 19.7% | 4.55% | 96% | T5o 44 J3o 33 Q2o J2o |
| F-C-R3.0 | SB | 12.6% | 1.72% | 41% | KTs J7s T5s K2o |

### 20bb, E+ : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 71.9% | 29.03% | 100% | AQs AJs A2s KK K9s K8s K6s QJs QTs J8s J7s J2s QTo TT T5s (+32) |
| root | BTN | 100.0% | 18.37% | 100% | AA AKs AJs A6s A5s A4s KK K9s K8s K7s K6s K5s QQ QJs QTs (+20) |
| R2.5-F | BB | 19.7% | 31.54% | 100% | A9s A8s A7s A5s KTs ATo T8s T2s 97s 93s 92s 87s 83s 82s Q7o (+33) |
| F-C | BB | 36.3% | 15.30% | 99% | A4s A3s A2s K5s K4s K3s QTs Q8s J3s J2s T9s T7s T6s T3s T2s (+22) |
| F-C-R3.0 | SB | 12.6% | 22.93% | 100% | KTs K9s K6s Q6s Q2s KJo J7s J4s T6s 95s 92s T8o 98o A7o A6o (+6) |

### 20bb, E- : nœuds les plus touchés

| Nœud | Acteur | Atteint | Écart moyen | Écart max | Mains qui changent |
|---|---|---|---|---|---|
| F | SB | 71.9% | 30.53% | 100% | AA AKs ATs A9s A8s A7s A6s A2s KQs KJs KTs K7s K6s AQo QQ (+42) |
| root | BTN | 100.0% | 14.23% | 100% | AQs AJs A5s A4s A3s A2s AKo KQs KJs KTs K9s K8s K7s K6s AQo (+17) |
| F-C | BB | 36.3% | 20.23% | 100% | A9s A6s A5s AKo K5s K4s K3s K2s AQo KQo QJs AJo KJo QJo JTs (+29) |
| R2.5-F | BB | 19.7% | 22.22% | 100% | AA ATs K7s K6s K5s KQo J9s J8s T9s 99 98s 88 77 66 55 (+17) |
| F-C-R3.0 | SB | 12.6% | 19.54% | 98% | AA A3s KK KTs J8s J3s J2s JTo T5s T4s T3s T2s 94s 93s 92s (+11) |
