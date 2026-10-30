# PLAN — Doctor Mesh (Roadmap & Lista TO-DO Atualizada)

> **Nota de Auditoria:** O código base do `ai_mesh_doctor` v0.2.0 foi incorporado com sucesso ao projeto. Diversos componentes de Scanner, Diagnóstico Topológico, Projeção em Plano, UI no Blender e Transações com Rollback já estavam implementados e testados. A lista abaixo foi atualizada marcando com `[x]` as tarefas cumpridas e mantendo como `[ ]` as tarefas pendentes de evolução e implementação.

---

## Estrutura Geral das Entregas

```
[ ENTREGA A: Provar a Reconstrução Geométrica ]
   ├── Fase 1: Auditoria, Ambiente e Dependências Mínimas [CONCLUÍDA]
   ├── Fase 2: Pesquisa e Algoritmos de Referência [EM ANDAMENTO]
   ├── Fase 3: Datasets Sintéticos e Suíte de Benchmark [EM ANDAMENTO]
   ├── Fase 4: Scanner Geométrico e Análise Topológica [CONCLUÍDA]
   └── Fase 5: Reconhecimento de Primitivas (Plano & Cilindro) [PRÓXIMO FOCO]
   Meta: Provar matematicamente que o sistema recupera a geometria de planos e cilindros deformados sem destruir bordas.

[ ENTREGA B: Motor de Reparo Autônomo e Desempenho ]
   ├── Fase 6: Motor de Reparação Geométrica Adaptativa (Plano OK / Cilindro Pendente)
   ├── Fase 7: Otimizador de Parâmetros e Função de Custo
   ├── Fase 8: Aceleração CUDA (NVIDIA Warp / GPU RTX 5050)
   └── Fase 9: Validação contra Regressões e Redução Poligonal

[ ENTREGA C: Produto Integrado e Assistência Inteligente ]
   ├── Fase 10: Addon do Blender (Interface & Viewport Visual) [BASE PRONTA]
   ├── Fase 11: Refinamento Semântico Multimodal (Supervisão Humana)
   └── Fase 12: Validação com Modelos Reais de IA e Release Final
```

---

## Checklist Detalhado e Status por Fase

### FASE 1: Auditoria, Ambiente e Dependências Mínimas
- [x] **1.1** Definir ambiente Python (compatível com Blender 4.2+ / 5.4 e Python 3.11+ no Windows). *(Concluído: validado na v0.2.0)*
- [x] **1.2** Criar manifesto de dependências base (`requirements-ai.txt` e dependências nativas `bpy`, `bmesh`, `mathutils`, `numpy`). *(Concluído)*
- [x] **1.3** Estruturar diretórios do projeto (`ai_mesh_doctor/`, `tests/`, `scripts/`, `examples/`, `docs/`, `reports/`). *(Concluído)*
- [x] **1.4** Modelo de dados e abstração de malha (`bmesh`, `arrays.py`, fingerprints e hashing de estado). *(Concluído na camada Blender)*
- [x] **1.5** Configurar suíte de testes automatizados (`tests/test_blender.py`, `tests/test_repair.py`, runner `scripts/run_tests.ps1`). *(Concluído)*
> **Status da Fase 1:** **100% CONCLUÍDA.**

---

### FASE 2: Pesquisa e Algoritmos de Referência
- [ ] **2.1** Estudar e implementar Taubin Smoothing ($\lambda/\mu$ bicíclico para evitar contração de volume em áreas orgânicas). *(Pendente: o código atual possui apenas Laplaciano restrito)*
- [ ] **2.2** Estudar e implementar Bilateral Normal Filtering para denoising com preservação de arestas. *(Pendente)*
- [x] **2.3** Avaliar implementações de KD-Tree para consultas espaciais de vizinhança. *(Concluído: `mathutils.kdtree.KDTree` integrado em `geometry.py`)*
- [x] **2.4** Definir formulação matemática de ajuste de plano por PCA / SVD e autovetores. *(Concluído: `measured_plane` em `repair.py` via `np.linalg.eigh`)*
- [ ] **2.5** Definir formulação matemática de ajuste robusto de cilindro (eixo diretor, ponto central e raio ótimo). *(Pendente: `quality.py` apenas valida, falta o estimador)*
> **Status da Fase 2:** Parcialmente concluída (2/5).

---

### FASE 3: Datasets Sintéticos e Suíte de Benchmark
- [x] **3.1** Gerador de malhas de teste canônicas (cubos, quads, planos em `tests/test_blender.py` e `tests/test_repair.py`). *(Concluído)*
- [ ] **3.2** Gerador paramétrico de deformações e defeitos controlados em cilindros e superfícies curvas (ruído Gaussiano, amassados intencionais). *(Pendente)*
- [x] **3.3** Casos de teste negativos: assimetria intencional (`test_intentional_asymmetry_not_a_defect`), malhas limpas recusadas em reparo (`test_clean_mesh_rejected_as_unnecessary`). *(Concluído)*
- [x] **3.4** Métricas objetivas de medição de qualidade: resíduo planar RMS (`rms_world`), desvio de planaridade e cálculo de volume assinado por tetraedros (`signed_volume_world`). *(Concluído)*
- [x] **3.5** Script automatizado de execução e relatório do benchmark (`tests/test_efficiency.py`, `scripts/run_tests.ps1`). *(Concluído)*
> **Status da Fase 3:** Parcialmente concluída (4/5).

---

### FASE 4: Scanner Geométrico e Análise Topológica
- [x] **4.1** Extrator de topologia: verificação de conectividade (`connected_components`), bordas abertas (`boundary_regions`), radial non-manifold, vértices soltos, arestas soltas (wire), faces degeneradas e winding inconsistente. *(Concluído em `geometry.py`)*
- [x] **4.2** Cálculo vetorizado de normais de faces e vértices. *(Concluído em `geometry.py` e `bmesh.normal_update()`)*
- [x] **4.3** Cálculo de ângulos diedrais entre faces adjacentes e detecção de bordas vivas (`e.calc_face_angle(0) < 30°`). *(Concluído)*
- [x] **4.4** Índice de vizinhança espacial com KDTree balanceada para pares duplicados e buscas por raio. *(Concluído em `geometry.py`)*
- [x] **4.5** Segmentação preliminar em ilhas e regiões de fronteira identificadas com fingerprints únicos e imutáveis. *(Concluído em `geometry.py` e `identity.py`)*
> **Status da Fase 4:** **100% CONCLUÍDA.**

---

### FASE 5: Reconhecimento de Primitivas Primárias
- [x] **5.1** Ajuste e projeção de planos com medição de resíduo RMS por PCA / Eigh em regiões da malha (`measured_plane` em `repair.py`). *(Concluído)*
- [ ] **5.2** RANSAC / Segmentação autônoma de múltiplos planos em malha sem necessidade de seleção manual prévia de índices. *(Pendente)*
- [ ] **5.3** Ajuste robusto de cilindros (recuperação automática de eixo diretor, raio $r$ e centro a partir de nuvem de pontos com ruído). *(Pendente)*
- [x] **5.4** Verificação geométrica de regiões contra tolerâncias de plano e cilindro (`check_surface` em `quality.py`). *(Concluído)*
- [ ] **5.5** Classificador formal de regiões (`PLANE`, `CYLINDER`, `FREEFORM`, `AMBIGUOUS`). *(Pendente)*
> **Status da Fase 5:** Parcialmente concluída (2/5). **[PRÓXIMO FOCO TÉCNICO]**

---

### FASE 6: Motor de Reparação Geométrica Adaptativa
- [x] **6.1** Projeção restrita para planos (`fit_plane` com parâmetro `strength` em `repair.py`). *(Concluído)*
- [ ] **6.2** Projeção restrita para cilindros (correção radial de vértices em relação ao eixo ajustado). *(Pendente)*
- [ ] **6.3** Máscara de atenuação suave (*falloff* ponderado) nas fronteiras das regiões reparadas. *(Pendente)*
- [ ] **6.4** Denoising Taubin para regiões classificadas como `FREEFORM`. *(Pendente)*
- [x] **6.5** Preservação estrita de bordas vivas, cantos e vértices de contorno durante suavizações (`movable` em `repair.py`). *(Concluído)*
- [x] **6.6** Execução em cópia segura (`RepairTransaction`) com garantia de não-destrutividade, validação prévia e rollback funcional. *(Concluído)*
> **Status da Fase 6:** Parcialmente concluída (3/6).

---

### FASE 7: Otimizador Autônomo e Função de Custo
- [x] **7.1** Função de validação de mudanças (`validate_change` em `validation.py`) com limites de deslocamento, dimensões e topologia. *(Concluído)*
- [ ] **7.2** Otimizador de hiperparâmetros (busca automática de iterações e força sem ajuste manual pelo usuário). *(Pendente)*
- [x] **7.3** *Safety Gate*: bloqueio automático de aplicação se os limites de tolerância forem violados. *(Concluído em `RepairTransaction.apply`)*
> **Status da Fase 7:** Parcialmente concluída (2/3).

---

### FASE 8: Aceleração CUDA e Alto Desempenho
- [ ] **8.1** Integração de `warp-lang` (NVIDIA Warp) para aceleração geométrica. *(Pendente)*
- [ ] **8.2** Abstração `GeometryBackend` unificando CPU e CUDA. *(Pendente)*
- [ ] **8.3** Kernels CUDA para cálculos massivos de resíduos e distâncias na GPU RTX 5050. *(Pendente)*
- [ ] **8.4** Fallback automático CPU $\longleftrightarrow$ GPU. *(Pendente)*
> **Status da Fase 8:** Pendente (0/4).

---

### FASE 9: Validação e Redução Poligonal
- [ ] **9.1** Decimação seletiva baseada em curvatura (preservar planos e cilindros reconstruídos). *(Pendente)*
- [x] **9.2** Recálculo de normais e verificação de UVs e materiais após reparação (`state_signature` em `repair.py`). *(Concluído)*
- [ ] **9.3** Pipeline de transferência/baking High-to-Low Poly. *(Pendente)*
> **Status da Fase 9:** Parcialmente concluída (1/3).

---

### FASE 10: Addon do Blender e Operação Integrada
- [x] **10.1** Registro e estrutura de Addon (`ai_mesh_doctor/__init__.py`). *(Concluído)*
- [x] **10.2** Operadores de Scan, Quick Preview, Repair, Rollback e Inspection. *(Concluído)*
- [x] **10.3** Painel na 3D Viewport (`ui.py`) com abas e controle de inspeção. *(Concluído)*
- [x] **10.4** Modo headless via script CLI (`scripts/scan_project.py`). *(Concluído)*
> **Status da Fase 10:** **100% CONCLUÍDA NA VERSÃO ATUAL.**

---

### FASE 11: Refinamento Semântico e Assistência Multimodal
- [x] **11.1** Captura multiview sistemática de 16 e 124 ângulos (`capture.py`). *(Concluído)*
- [x] **11.2** Integração com SDK OpenAI estruturado e contagem de tokens sem chamadas desnecessárias (`ai_client.py`). *(Concluído)*
- [x] **11.3** Proposta assistida com confirmação humana obrigatória e persistência em SQLite (`knowledge.py`). *(Concluído)*
> **Status da Fase 11:** **100% CONCLUÍDA NA VERSÃO ATUAL.**

---

### FASE 12: Validação Final, Benchmarks Reais e Release
- [x] **12.1** Pacote de distribuição gerado (`dist/ai_mesh_doctor-0.2.0.zip`). *(Concluído)*
- [x] **12.2** Arquivo de projeto de demonstração (`project/AI_Mesh_Doctor_Demo.blend`). *(Concluído)*
- [ ] **12.3** Bateria de testes em modelos gerados por IA (Tripo3D / TRELLIS) com peças mecha completas. *(Pendente)*
> **Status da Fase 12:** Parcialmente concluída (2/3).
