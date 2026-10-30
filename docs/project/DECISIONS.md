# DECISIONS — Doctor Mesh

## Registro de Decisões Técnicas

### [DEC-001] Inicialização do Repositório e Documentação Operacional
- **Data:** 30/10/2026
- **Contexto:** Inicialização controlada do projeto conforme o contrato do Master Prompt.
- **Decisão:** Inicializar o Git (`git init`) e criar a pasta `docs/project/` contendo `PROJECT.md`, `ARCHITECTURE.md`, `PLAN.md`, `STATE.md` e `DECISIONS.md`.
- **Justificativa:** Garantir rastreabilidade, persistência de contexto entre sessões e conformidade estrita com o protocolo de orquestração técnica antes do início da escrita de código.
- **Impacto:** Todas as decisões e estados operacionais serão rastreados diretamente no repositório.

---

### [DEC-002] Arquitetura Desacoplada: Headless Core vs. Thin-Client Blender
- **Data:** 30/10/2026
- **Contexto:** Necessidade de desenvolver algoritmos avançados de geometria 3D com alta testabilidade, automação e benchmarking.
- **Decisão:** Separar o projeto em duas camadas estritas:
  1. `mesh_core/`: Pacote Python independente sem qualquer dependência de `bpy` (API do Blender), utilizando `numpy`, `scipy` e tensores puros.
  2. `blender_addon/`: Casca fina de interface de usuário que apenas consome o `mesh_core`, mapeando estruturas `BMesh` de/para arrays.
- **Justificativa:** Executar o Blender para cada teste de unidade adiciona overhead de segundos/minutos. Um core independente permite rodar milhares de testes e benchmarks sintéticos em milissegundos via `pytest` ou CLI headless.
- **Impacto:** Alta cobertura de testes automatizados, portabilidade para servidores e pipelines em lote.

---

### [DEC-003] Regra de Ouro: Processamento 100% Local (CPU + GPU RTX 5050)
- **Data:** 30/10/2026
- **Contexto:** Modelos 3D de alta densidade gerados por IA exigem alto poder computacional e privacidade de propriedade intelectual.
- **Decisão:** Toda a computação geométrica (análise, fitting RANSAC, Taubin, projeções e métricas) será executada 100% localmente no computador do usuário, utilizando CPU (NumPy/SciPy) com aceleração paralela opcional na GPU NVIDIA RTX 5050 via NVIDIA Warp. LLMs ou modelos multimodais remotos nunca calcularão geometria.
- **Justificativa:** Elimina custos recorrentes de API de nuvem, garante privacidade total dos modelos e assegura tempos de resposta de milissegundos.
- **Impacto:** O projeto deve manter paridade estrita entre os backends `CpuBackend` e `CudaBackend`.

---

### [DEC-004] Estratégia de Entrega Incremental em 3 Marcos
- **Data:** 30/10/2026
- **Contexto:** O escopo completo abrange desde processamento matemático básico até aceleração CUDA e IA multimodal.
- **Decisão:** Dividir a execução em 3 marcos objetivos e sequenciais:
  - **Entrega A (Fases 1 a 5):** Provar a reconstrução geométrica em placas e cilindros deformados (Scan + Segmentação + Fitting).
  - **Entrega B (Fases 6 a 9):** Motor de reparo autônomo, otimizador com rollback e aceleração CUDA na RTX 5050.
  - **Entrega C (Fases 10 a 12):** Addon completo no Blender, visualização de mapas de calor, inspeção multimodal e release v1.0.
- **Justificativa:** Impede o overengineering prematuro. Não se constrói interface ou GPU kernels antes de provar matematicamente que os algoritmos de reconstrução convergem.
- **Impacto:** Execução estritamente faseada com critérios claros de parada e validação.
