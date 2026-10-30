# PROJECT — Doctor Mesh (AI Mesh Doctor)

## 1. Visão Geral e Propósito do Sistema

O **Doctor Mesh** (originalmente concebido como *AI Mesh Doctor*) é um sistema de reconstrução e refinamento geométrico de alta fidelidade desenvolvido especificamente para **modelos 3D gerados por Inteligência Artificial** (tais como Tripo3D, TRELLIS.2, Pixal3D, ComfyUI Image-to-3D, etc.).

### O Problema Real
Modelos 3D gerados por IA generativa produzem bases volumétricas excelentes, porém frequentemente apresentam imperfeições geométricas inaceitáveis para uso profissional e manufatura:
- Superfícies que deveriam ser perfeitamente planas ou cilíndricas (em peças *hard-surface*, mechas e robótica) apresentam ondulações, amassados, sulcos e rugosidade aleatória.
- Normais de vértices e faces inconsistentes, invertidas ou com suavização errônea.
- Topologias defeituosas (vértices duplicados, buracos, faces sobrepostas, componentes desconectados e malhas *non-manifold*).
- A aplicação ingênua de um operador global de *Smooth* (suavização uniforme) destrói cantos vivos, chanfros, juntas mecânicas e a silhueta original do modelo.

### A Solução
Construir um pipeline autônomo e determinístico que execute o ciclo:
$$\text{Scan} \longrightarrow \text{Segmentação} \longrightarrow \text{Reconhecimento de Primitivas} \longrightarrow \text{Detecção de Defeitos} \longrightarrow \text{Reparo Adaptativo} \longrightarrow \text{Validação}$$

O sistema reconhece a **intenção geométrica** por trás da superfície (plano, cilindro, cone, esfera ou forma livre orgânica), repara apenas as anomalias locais por projeção restrita e filtragem bilateral, e valida a saída contra regressões de volume e bordas.

---

## 2. Princípios e Regras Fundamentais Inegociáveis

1. **Nunca Destruir o Original:** Todas as operações ocorrem em cópias reversíveis ou malhas candidatas em memória isolada.
2. **Não Confundir *Smooth* com Reparação:** Primeiro entende-se a intenção geométrica da região; depois seleciona-se a estratégia matemática correspondente.
3. **Nunca Corrigir sem Validar:** Uma superfície com menor rugosidade não é necessariamente melhor. Toda alteração passa por métricas de fidelidade, desvio Hausdorff e preservação de volume.
4. **Processamento 100% Local:** Todo o cálculo numérico, ajuste de superfícies e reparação geométrica rodam exclusivamente no computador local (CPU e aceleração NVIDIA CUDA na GPU RTX 5050), sem dependência de APIs remotas para a geometria.
5. **Tolerância a Ambiguidades:** Se uma região não possuir confiança estatística suficiente para classificação, o sistema **não** aplica alterações arbitrárias.
6. **Reutilização Inteligente (KISS / Anti-Overengineering):** Não reinventar algoritmos numéricos do zero; aproveitar bibliotecas consolidadas da indústria (Open3D, PyMeshLab, SciPy, BMesh, NVIDIA Warp).

---

## 3. Requisitos Funcionais

### RF-01: Scanner Geométrico e Diagnóstico Topológico
- Extração de matrizes de vértices, faces, arestas e atributos.
- Identificação de topologia inválida: bordas *non-manifold*, buracos, faces degeneradas (área zero) e componentes desconectados.
- Cálculo de propriedades diferenciais: normais ponderadas, curvaturas principais (Gaussiana e Média) e ângulos diedrais entre faces adjacentes.
- Construção de índice espacial (KD-Tree / BVH) para buscas rápidas de vizinhança $\mathcal{O}(\log N)$.

### RF-02: Segmentação e Reconhecimento de Formas Primárias
- Agrupamento de faces em regiões coerentes através de coerência de normais e curvatura.
- Ajuste robusto de primitivas canônicas (RANSAC e mínimos quadrados):
  - Planos ($ax + by + cz + d = 0$).
  - Cilindros (eixo diretor, ponto central e raio $r$).
  - Esferas e cones.
- Cálculo de resíduos estatísticos e índice de confiança por região.
- Classificação de regiões livres (*freeform*) e proteção explícita de bordas vivas (*creases*, *sharp edges*).

### RF-03: Motor de Reparação Adaptativa Local
- **Ajuste Restrito:** Projeção ortogonal controlada de vértices imperfeitos sobre a primitiva matemática reconhecida.
- **Denoising com Preservação de Bordas:** Algoritmos Taubin (suavização sem encolhimento de volume) e Bilateral Normal Filtering.
- Máscaras de influência ponderadas (*falloff* suave nas fronteiras entre regiões reparadas e não reparadas).
- Preenchimento de furos e reparação topológica localizada.

### RF-04: Otimizador Autônomo e Validação de Métricas
- Função de custo multiobjetivo combinando:
  - Regularidade da superfície (redução de resíduos locais).
  - Fidelidade à intenção original (preservação do volume global $\Delta V < \epsilon$).
  - Preservação da silhueta e distâncias máximas de deslocamento de vértices.
- Mecanismo de rejeição e rollback automático se a malha candidata violar restrições.

### RF-05: Redução Poligonal e Preparação de Assets
- Decimação / retopologia inteligente mantendo a fidelidade das superfícies reconstruídas.
- Suporte a geração de mapas normais / baking de High Poly corrigido para Low Poly utilizável.

### RF-06: Interface Blender e Modo Headless
- Operação desvinculada de interface gráfica (modo headless/CLI) para pipelines automatizados, benchmarks e testes de regressão.
- Addon integrado para Blender 4.x/5.x com painel lateral:
  - Abas: *Scan*, *Diagnose*, *Repair*, *Validate*, *Export*.
  - Mapas de calor (Vertex Colors / Attribute Maps) indicando defeitos e resíduos diretamente na viewport 3D.

---

## 4. Requisitos Não-Funcionais e Restrições Técnicas

- **Ambiente Operacional:** Windows 11 x64.
- **Hardware Alvo:** Processador moderno com GPU dedicada NVIDIA GeForce RTX 5050 (Arquitetura Blackwell / CUDA Compute Capability moderna).
- **Linguagem Base:** Python 3.10+ (compatível com os runtimes internos do Blender 4.2 LTS / 4.3+).
- **Desacoplamento Arquitetural:** O núcleo matemático (`mesh_core`) não pode possuir dependência rígida de `bpy` (API do Blender), garantindo portabilidade para execução em scripts CLI, serviços em lote e testes de unidade rápidos.
- **Aceleração Opcional e Fallback:** O pipeline deve possuir paridade exata de resultados entre o backend CPU (NumPy/SciPy/Open3D) e o backend GPU acelerado (CUDA / NVIDIA Warp). Na ausência de GPU, o fallback para CPU é automático.
