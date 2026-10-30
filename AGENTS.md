# AGENTS.md — Contrato Operacional de Engenharia

Este documento estabelece as diretrizes permanentes de desenvolvimento para este repositório. Todas as análises, decisões técnicas, revisões, refatorações e implementações realizadas por agentes ou desenvolvedores devem obedecer rigorosamente a estas regras.

---

## 1. Princípio Fundamental: O Ônus da Justificativa

> **Nenhum componente, abstração, dependência, camada arquitetural ou padrão de projeto deve existir sem uma necessidade concreta que justifique sua presença.**

1. A complexidade adicional carrega o **ônus da prova**: sempre que uma implementação direta atender integralmente aos requisitos, ela deverá ser preferida em relação a soluções indiretas ou elaboradas.
2. Não introduza interfaces, camadas (ex.: *controllers*, *services*, *repositories*, *adapters*), *factories*, *wrappers* ou estruturas genéricas apenas por convenção, estética ou suposições de extensibilidade futura.
3. Cenários hipotéticos de escalabilidade, expansão de funcionalidades ou reuso futuro **não** constituem justificativa técnica aceitável.
4. Uma solução mais abstrata só será implementada quando sua necessidade for comprovada por:
   - Requisitos funcionais ou não-funcionais atuais;
   - Uma evolução de arquitetura formalmente aprovada e documentada;
   - Eliminação de duplicação real e custosa de código comprovada na prática.

---

## 2. Regras Operacionais para Agentes

Ao planejar ou implementar qualquer alteração, o agente deve seguir obrigatoriamente este fluxo:

1. **Compreensão Precedente:** Compreender o problema, os requisitos explícitos e as restrições antes de propor ou gerar código.
2. **Inspeção do Contexto:** Investigar a base de código existente, reutilizando utilitários, convenções e mecanismos já disponíveis.
3. **Menor Solução Correta:** Priorizar a menor implementação que seja correta, legível, coesa, testável e sustentável.
4. **Anti-Generalização Prematura:** Não criar classes genéricas, tipos parametrizados complexos ou soluções universais para problemas que ocorrem em um único ponto.
5. **Anti-Infraestrutura Antecipada:** Não configurar filas, caches, conexões com serviços externos ou módulos auxiliares antes que o fluxo principal dependa concretamente deles.
6. **Consulta a Padrões Oficiais:** Basear-se na documentação oficial das ferramentas utilizadas e em precedentes consolidados da linguagem antes de criar lógicas personalizadas.
7. **Simplicidade != Inferioridade:** Não interpretar código direto e linear como simplista ou inferior a soluções que utilizam múltiplos níveis de indireção.
8. **Isolamento de Escopo:** Preservar estritamente o comportamento preexistente. Não realizar refatorações paralelas, renomeações em massa ou alterações fora do escopo solicitado.
9. **Abstrações Justificadas:** Introduzir abstrações apenas quando eliminarem complexidade real e trouxerem benefício técnico verificável e proporcional.
10. **Tolerância Zero a Suposições:** Não inferir preferências técnicas ou requisitos não declarados. Se houver ambiguidade impeditiva, interromper e solicitar esclarecimento formal.

---

## 3. Diretrizes de Qualidade e Boas Práticas

A busca pela simplicidade **não proíbe** boas práticas de engenharia:

- **Modularização:** Separe arquivos e módulos quando a responsabilidade justificar o isolamento lógico e a legibilidade.
- **Testes:** Todo código deve ser testável. Teste o comportamento e as regras de negócio, evitando testes excessivos focados apenas em implementações internas efêmeras.
- **Tratamento de Erros:** Trate falhas de forma explícita e determinística; evite capturas genéricas que silenciem comportamentos anômalos.
- **Segurança e Desempenho:** Eficiência de recursos e proteção de dados são requisitos primários e não devem ser negligenciados em prol da brevidade.

---

## 4. Checklist Pré-Implementação

Antes de finalizar qualquer modificação, responda:
- [ ] Esta implementação introduziu alguma camada, classe ou arquivo que poderia ser omitido mantendo a correção?
- [ ] Todas as dependências adicionadas são indispensáveis para os requisitos atuais?
- [ ] A solução resolve o problema de hoje sem antecipar o de amanhã?
- [ ] O escopo da alteração limitou-se ao que foi explicitamente solicitado?
