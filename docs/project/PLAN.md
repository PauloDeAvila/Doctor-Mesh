# PLAN — Doctor Mesh (Roadmap & Lista TO-DO de Implementação)

Este documento estabelece o planejamento sequencial do projeto, dividido em 3 Grandes Entregas e 12 Fases de desenvolvimento incremental.

---

## Estrutura Geral das Entregas

```
[ ENTREGA A: Provar a Reconstrução Geométrica ]
   ├── Fase 1: Auditoria, Ambiente e Dependências Mínimas
   ├── Fase 2: Pesquisa e Algoritmos de Referência
   ├── Fase 3: Datasets Sintéticos e Suíte de Benchmark
   ├── Fase 4: Scanner Geométrico e Análise Topológica
   └── Fase 5: Reconhecimento de Primitivas (Plano & Cilindro)
   Meta: Provar matematicamente que o sistema recupera a geometria de planos e cilindros deformados sem destruir bordas.

[ ENTREGA B: Motor de Reparo Autônomo e Desempenho ]
   ├── Fase 6: Motor de Reparação Geométrica Adaptativa
   ├── Fase 7: Otimizador de Parâmetros e Função de Custo
   ├── Fase 8: Aceleração CUDA (NVIDIA Warp / GPU RTX 5050)
   └── Fase 9: Validação contra Regressões e Redução Poligonal
   Meta: O sistema detecta os defeitos e aplica o reparo ideal de forma autônoma com alta velocidade em GPU.

[ ENTREGA C: Produto Integrado e Assistência Inteligente ]
   ├── Fase 10: Addon do Blender (Interface & Viewport Visual)
   ├── Fase 11: Refinamento Semântico Multimodal (Supervisão Humana)
   └── Fase 12: Validação com Modelos Reais de IA e Release Final
   Meta: Produto completo empacotado, testado com modelos reais do Tripo3D/TRELLIS.2 e documentado.
```

---

## Checklist Detalhado e Tarefas por Fase

### FASE 1: Auditoria, Ambiente e Dependências Mínimas
- [ ] **1.1** Definir ambiente Python (versão compatível com o ecossistema e Blender 4.2+).
- [ ] **1.2** Criar manifesto de dependências base (`pyproject.toml` ou `requirements.txt`) contendo apenas: `numpy`, `scipy`, `trimesh` ou `open3d`.
- [ ] **1.3** Estruturar diretórios do projeto (`mesh_core`, `tests`, `benchmarks`).
- [ ] **1.4** Criar modelo de dados canônico (`MeshModel`) desacoplado de interfaces gráficas.
- [ ] **1.5** Configurar suíte de testes automatizados (`pytest`).
> **Critério de Aceitação:** Ambiente virtual configurado, estrutura de diretórios criada e teste de unidade básico do `MeshModel` executando com sucesso em modo headless.

---

### FASE 2: Pesquisa e Algoritmos de Referência
- [ ] **2.1** Estudar e documentar propriedades de Taubin Smoothing (evitar contração de volume).
- [ ] **2.2** Estudar e documentar Bilateral Normal Filtering para preservação de bordas e descontinuidades.
- [ ] **2.3** Avaliar implementações de KD-Tree para consultas espaciais ultrarrápidas de vizinhança.
- [ ] **2.4** Definir formulação matemática de ajuste de plano por PCA / SVD e RANSAC.
- [ ] **2.5** Definir formulação matemática de ajuste de cilindro (eixo ortogonal, ponto e raio ótimo).
> **Critério de Aceitação:** Documento de algoritmos e protótipos matemáticos executáveis isolados em scripts de teste.

---

### FASE 3: Datasets Sintéticos e Suíte de Benchmark
- [ ] **3.1** Implementar gerador paramétrico de malhas de teste canônicas (placas perfeitamente planas e cilindros perfeitos).
- [ ] **3.2** Implementar gerador de defeitos controlados: injeção de ruído Gaussiano, amassados (*dents*) e deformações sinusoidais.
- [ ] **3.3** Criar casos de teste negativos: modelos com chanfros intencionais, relevos ou sulcos que **não devem** ser suavizados.
- [ ] **3.4** Implementar métricas objetivas de medição de qualidade:
  - Resíduo de primitivas (distância dos vértices à superfície ideal).
  - Variação relativa de volume ($\Delta V / V_0$).
  - Desvio de Hausdorff antes e após a intervenção.
- [ ] **3.5** Implementar script automatizado de execução e relatório do benchmark.
> **Critério de Aceitação:** Benchmark reproduzível gerando malhas sintéticas com defeitos conhecidos e calculando métricas objetivas de erro.

---

### FASE 4: Scanner Geométrico e Análise Topológica
- [ ] **4.1** Implementar extrator de topologia: verificação de conectividade, bordas *manifold*, furos e orientação de faces.
- [ ] **4.2** Implementar cálculo vetorizado de normais de faces e normais de vértices ponderadas por ângulo.
- [ ] **4.3** Implementar cálculo de ângulos diedrais entre faces adjacentes para detecção de bordas vivas (*sharp edges*).
- [ ] **4.4** Construir índice de vizinhança espacial (KD-Tree de vértices e centroides de faces).
- [ ] **4.5** Implementar segmentação preliminar da malha em regiões geométricas suaves delimitadas por bordas vivas.
> **Critério de Aceitação:** O scanner processa uma malha arbitrária e gera mapas de descontinuidades, bordas protegidas e regiões candidatas sem modificar a geometria.

---

### FASE 5: Reconhecimento de Primitivas Primárias
- [ ] **5.1** Implementar RANSAC robusto para detecção e ajuste de planos em regiões candidatas.
- [ ] **5.2** Implementar algoritmo robusto para detecção e ajuste de cilindros (determinação de eixo diretor e raio).
- [ ] **5.3** Calcular resíduos e score de confiança estatística ($R^2$ / variância residual) para cada primitiva encontrada.
- [ ] **5.4** Classificar formalmente cada região da malha:
  - `PLANE` (alta confiança em plano)
  - `CYLINDER` (alta confiança em cilindro)
  - `FREEFORM` (região orgânica ou sem primitiva clara)
  - `AMBIGUOUS` (confiança insuficiente — marcada como protegida de alterações automáticas).
> **Critério de Aceitação:** O sistema recebe uma placa deformada e um cilindro amassado e identifica corretamente a equação e o tipo de cada forma, isolando os vértices que estão fora da geometria pretendida.

---

### FASE 6: Motor de Reparação Geométrica Adaptativa
- [ ] **6.1** Implementar projeção restrita para planos: deslocamento dos vértices anômalos até o plano ajustado.
- [ ] **6.2** Implementar projeção restrita para cilindros: correção radial dos vértices em relação ao eixo e raio ajustados.
- [ ] **6.3** Implementar máscara de atenuação suave (*falloff* ponderado) nas fronteiras das regiões reparadas para evitar degraus.
- [ ] **6.4** Implementar algoritmo Taubin e Bilateral Smoothing para regiões classificadas como `FREEFORM`.
- [ ] **6.5** Garantir preservação estrita dos vértices classificados como bordas vivas ou cantos mecânicos.
- [ ] **6.6** Implementar execução em cópia de segurança (`clone`) com garantia de não-destrutividade.
> **Critério de Aceitação:** O sistema repara uma placa e um cilindro sintéticos deformados, alcançando resíduos inferiores ao modelo original e preservando as bordas sem contrair volume.

---

### FASE 7: Otimizador Autônomo e Função de Custo
- [ ] **7.1** Formular função de custo multiobjetivo combinando:
  - Minimização de rugosidade / resíduo.
  - Penalidade por alteração de volume.
  - Penalidade por deslocamento de vértices em bordas protegidas.
- [ ] **7.2** Implementar busca automática de hiperparâmetros (número de iterações, fatores de amortecimento $\lambda$ e $\mu$).
- [ ] **7.3** Implementar mecanismo de *Safety Gate*: se a malha candidata resultar em auto-interseção ou aumento da função de custo, abortar e aplicar rollback automático.
> **Critério de Aceitação:** O otimizador escolhe e aplica sozinho os parâmetros ideais sem intervenção humana, rejeitando automaticamente tentativas que degradem a malha.

---

### FASE 8: Aceleração CUDA e Alto Desempenho
- [ ] **8.1** Avaliar e configurar `warp-lang` (NVIDIA Warp) para aceleração de geometria em GPU.
- [ ] **8.2** Implementar `GeometryBackend` unificado com instâncias `CpuBackend` e `CudaBackend`.
- [ ] **8.3** Portar para CUDA os cálculos massivos: normais, distâncias ponto-plano/cilindro e iterações de Taubin.
- [ ] **8.4** Implementar fallback automático para CPU caso nenhuma GPU compatível ou driver CUDA seja detectado.
- [ ] **8.5** Medir e comparar velocidade, consumo de memória e paridade numérica exata entre CPU e GPU RTX 5050.
> **Critério de Aceitação:** Aceleração GPU ativa com ganho de desempenho comprovado em malhas densas (> 100k vértices) e resultados idênticos aos da CPU.

---

### FASE 9: Validação e Redução Poligonal
- [ ] **9.1** Implementar rotina de decimação seletiva baseada em curvatura (reduzir densidade em áreas planas, manter densidade em bordas e curvas).
- [ ] **9.2** Implementar recálculo consistente de normais ponderadas e verificação de integridade de UVs.
- [ ] **9.3** Criar fluxo de transferência de detalhes / baking de High Poly corrigido para Low Poly otimizado.
> **Critério de Aceitação:** Geração de versão Low Poly otimizada para jogos/render, preservando as superfícies planas e cilíndricas corrigidas na etapa de alta resolução.

---

### FASE 10: Addon do Blender e Operação Integrada
- [ ] **10.1** Criar estrutura padrão do Addon Blender 4.x (`__init__.py`, `blender_manifest.toml`).
- [ ] **10.2** Implementar ponte de dados bidirecional `BMesh` $\longleftrightarrow$ `MeshModel`.
- [ ] **10.3** Criar painel de interface de usuário na 3D Viewport com as etapas:
  - Aba 1: **Scan & Diagnóstico** (com visualização de mapas de calor na viewport).
  - Aba 2: **Classificação de Primitivas** (cores distintas por região identificada).
  - Aba 3: **Reparação Adaptativa** (sliders de sensibilidade com fallback automático).
  - Aba 4: **Validação e Comparação Antes/Depois** (slider de transparência ou alternância A/B).
  - Aba 5: **Exportação e Decimação**.
- [ ] **10.4** Suporte a modo *headless* por CLI do Blender para execução via scripts e pipelines em lote.
> **Critério de Aceitação:** O addon instala no Blender com 1 clique, escaneia o objeto selecionado na viewport, exibe os defeitos e aplica a correção de forma interativa.

---

### FASE 11: Refinamento Semântico e Assistência Multimodal
- [ ] **11.1** Implementar renderizador de capturas ortogonais multiview automáticas de regiões ambíguas.
- [ ] **11.2** Estruturar protocolo de diagnóstico visual para inspeção de padrões interrompidos (linhas de chapas, encaixes de mecha).
- [ ] **11.3** Implementar mecanismo de proposta com **confirmação humana obrigatória** (a IA sugere, o usuário confirma, o motor local executa).
> **Critério de Aceitação:** O sistema identifica uma descontinuidade semântica em uma peça mecânica, exibe proposta visual e só executa a modificação após confirmação explícita.

---

### FASE 12: Validação Final, Benchmarks Reais e Release
- [ ] **12.1** Executar bateria de testes em modelos reais complexos gerados por IA (outputs do Tripo3D e TRELLIS.2).
- [ ] **12.2** Testar estabilidade sob malhas densas (> 500k polígonos), cancelamentos de operação e tratamento de exceções.
- [ ] **12.3** Gerar documentação completa de instalação, requisitos e manual de uso do Addon.
- [ ] **12.4** Empacotar a versão release `v1.0.0` do Addon e do Core.
> **Critério de Aceitação:** Release consolidada, instalável, com testes de regressão passando e relatório de eficácia em modelos reais de IA.
