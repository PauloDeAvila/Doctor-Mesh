# ARCHITECTURE — Doctor Mesh

## 1. Visão Geral da Arquitetura

O sistema adota uma **Arquitetura Desacoplada e Modular**, separando estritamente a interface de visualização do motor de processamento numérico:

```
[ Blender Viewport / UI ] <-----> [ Adaptador BMesh ]
                                           |
                                  (Buffers Numéricos)
                                           |
                                           v
+--------------------------------------------------------------------------+
|                        mesh_core (Motor Independente)                    |
|                                                                          |
|  [ Estruturas de Dados ]  MeshModel (V, F, Normais, Arestas, KD-Tree)    |
|                                                                          |
|  [ Pipeline de Análise ]  Topologia -> Curvatura -> Segmentação          |
|                                                                          |
|  [ Motor de Reconhecimento ] Ajuste de Primitivas RANSAC (Planos, Cils)  |
|                                                                          |
|  [ Motor de Reparação ]   Projeção Restrita | Taubin | Bilateral Normals |
|                                                                          |
|  [ Validação & Métricas ] Desvio Hausdorff | Delta Volume | Rollback     |
+--------------------------------------------------------------------------+
        |                                                  ^
        |                                                  |
        +-----> Backend CPU (NumPy, SciPy, Open3D) --------+
        |
        +-----> Backend GPU (NVIDIA Warp / CUDA Kernels) --+
```

---

## 2. Princípios de Separação de Responsabilidades

### 2.1. O Núcleo Matemático (`mesh_core/`)
- **Independência Total do Blender:** O pacote `mesh_core` opera utilizando arrays contíguos de memória (`numpy.ndarray`) e estruturas geométricas padronizadas.
- **Por que essa decisão?** Permite executar testes de unidade, benchmarks em datasets sintéticos e pipelines em lote centenas de vezes mais rápido, sem o overhead de inicialização da interface gráfica do Blender.
- **Transição Transparente de Backends:** Uma abstração simples e estrita (`GeometryBackend`) com duas implementações equivalentes:
  1. `CpuBackend`: baseado em operações vetorizadas NumPy/SciPy e algoritmos Open3D.
  2. `CudaBackend`: baseado em NVIDIA Warp (`warp-lang`), compilando kernels JIT em CUDA para execução massivamente paralela na GPU RTX 5050.

### 2.2. A Camada de Integração com o Blender (`blender_addon/`)
- Atua como uma casca fina (*thin client*) de interface e orquestração.
- Converte geometrias `BMesh` em tensores/buffers para o `mesh_core` e reconstrói o `BMesh` com os resultados validados.
- Oferece controle visual via painel na aba lateral da 3D Viewport (`N-panel`) e mapas de vértice coloridos para inspeção de defeitos em tempo real.

---

## 3. Detalhamento do Pipeline em 6 Estágios

```
[1. SCAN] 
   └── Extrai vértices, conectividade e topologia.
   └── Constrói KD-Tree espacial e identifica bordas vivas (diedros > threshold).

[2. SEGMENTAÇÃO]
   └── Agrupamento regional de faces por similaridade de orientação e curvatura.
   └── Separação de ilhas e rotulagem de zonas livres versus candidatas a formas geométricas.

[3. AJUSTE DE PRIMITIVAS (PRIMITIVE FITTING)]
   └── Execução de RANSAC com estimativa de mínimos quadrados em cada região:
       - Planos: Ax + By + Cz + D = 0
       - Cilindros: Eixo diretor D, Origem P0, Raio R
   └── Cálculo de resíduo quadrático médio (RMSE) e score de confiança.

[4. DETECÇÃO DE DEFEITOS]
   └── Vértices com desvio acima da tolerância sigma em relação à primitiva ajustada são marcados como anomalias.
   └── Preservação estrita de vértices pertencentes a bordas vivas, cantos e marcas intencionais.

[5. REPARO ADAPTATIVO]
   └── Vértices defeituosos em superfícies canônicas: Projeção restrita na equação geométrica com máscara de atenuação suave na borda.
   └── Vértices em formas livres/orgânicas: Suavização por Taubin (evita encolhimento) ou filtragem bilateral de normais.

[6. VALIDAÇÃO & DECISÃO DE ROLLBACK]
   └── Comparação entre malha original e candidata:
       - |Volume_novo - Volume_orig| / Volume_orig < 1%
       - Max_Deslocamento_Vertice < Threshold_Segurança
       - Inexistência de faces auto-interseccionadas geradas.
   └── Se aprovado: Atualiza a malha.
   └── Se reprovado: Reverte para a versão original sem mutações colaterais.
```

---

## 4. Estrutura Canônica de Diretórios

```text
Doctor_Mesh/
├── AGENTS.md                   # Contrato operacional e regras de engenharia
├── docs/                       # Documentação e persistência de contexto
│   └── project/
│       ├── PROJECT.md          # Especificação de requisitos e regras de negócio
│       ├── ARCHITECTURE.md     # Decisões e diagramas arquiteturais
│       ├── PLAN.md             # Decomposição em Fases, Blocos e TO-DO lists
│       ├── STATE.md            # Estado operacional e tracking da sessão
│       └── DECISIONS.md        # Log cronológico de decisões técnicas
│
├── mesh_core/                  # Núcleo numérico e geométrico independente
│   ├── __init__.py
│   ├── model.py                # Modelo de dados da malha (V, F, N, atributos)
│   ├── spatial.py              # Índices espaciais e consultas KD-Tree
│   ├── analysis/
│   │   ├── topology.py         # Checagens manifold, componentes e buracos
│   │   ├── curvature.py        # Curvaturas médias, Gaussianas e diedros
│   │   └── segmentation.py     # Agrupamento e detecção de bordas vivas
│   ├── fitting/
│   │   ├── ransac_base.py      # Mecanismo básico de consenso RANSAC
│   │   ├── plane.py            # Ajuste de plano e resíduos
│   │   └── cylinder.py         # Ajuste de cilindro e raio
│   ├── repair/
│   │   ├── projection.py       # Projeção restrita a primitivas
│   │   ├── taubin.py           # Denoising Taubin sem encolhimento
│   │   └── bilateral.py        # Filtragem bilateral de normais
│   └── validation/
│       └── metrics.py          # Cálculo de Hausdorff, desvios e variação de volume
│
├── blender_addon/              # Extensão/Addon para o Blender (Thin Client)
│   └── doctor_mesh/
│       ├── __init__.py         # Registro do addon no Blender
│       ├── operators.py        # Operadores (Scan, Repair, Reset)
│       └── ui.py               # Painel na 3D Viewport
│
├── benchmarks/                 # Geradores de testes e dados de validação
│   ├── synthetic_generators.py # Criação de placas e cilindros com amassados sintéticos
│   └── run_benchmark.py        # Execução automatizada e comparação de métricas
│
└── tests/                      # Bateria de testes automatizados
    ├── test_topology.py
    ├── test_fitting.py
    └── test_repair.py
```

---

## 5. Justificativa das Dependências

Cada biblioteca externa a ser introduzida atende ao **Ônus da Prova**:
- `numpy`: Manipulação vetorizada contígua em C de matrizes de coordenadas e conectividade.
- `scipy`: KD-Tree (`scipy.spatial.cKDTree`) de alta velocidade e otimização de mínimos quadrados para ajuste de eixos e raios.
- `open3d` (ou `pymeshlab`/`trimesh`): Algoritmos validados pela comunidade para I/O e computação gráfica padrão.
- `warp-lang` (NVIDIA Warp): Compilação JIT de kernels Python para CUDA nativo na RTX 5050 sem a complexidade de compilar código C++/CUDA com MSVC.
