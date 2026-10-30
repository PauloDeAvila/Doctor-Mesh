# Falhas observadas e prevenção executável —0.2

Fonte: reconstrução real de tripo_part_0/3 em28/10/2026; resultado visual ainda pendente de aprovação. Não promover as reconstruções rejeitadas a receitas aprovadas.

| Falha | Prevenção implementada | Verificação |
|---|---|---|
| Descompactação NPZ a cada polígono bloqueou o Blender | `arrays.load_npz_arrays` retorna um dicionário materializado e fecha o arquivo; orçamento descompactado, índices e valores finitos verificados |19 regressões, incluindo1000 acessos com uma única leitura por membro |
| Medição repetida da base e da avaliada iguais | Conteúdo real em `scanner`, cache persistente com checksum/versionamento; material/UV inspecionados à parte |Análise fria/quente dos15 componentes reais; geometria, matriz, sharp, configuração e modificador alterados invalidam cache |
| Dados de um molde editado poderiam alimentar uma receita antiga | `validate_source_snapshot` compara coordenadas, conectividade/winding e matriz antes da prévia0/3 |Teste de molde, frame e faces alterados |
| Triângulos individualmente planos escondiam uma superfície enrugada | `check_surface` confere uma região inteira contra o plano ou eixo medido; o gerador registra regiões pelos índices de construção |Plano ondulado e círculo ovalizado são recusados |
| Cortador com extremidade coplanar deixou membrana numérica | `through_cut_interval` calcula margem além dos dois limites do estoque; colar3 usa os limites efetivos do material |Teste dos dois extremos e erro de corda; recortes cegos continuam separados |
| Colar/corpo duplicavam a parede cilíndrica interna | `inspect_coincident_interface` detecta superfícies quase coincidentes nos dois sentidos; somente contato oposto num plano declarado pode ser aceito |Superfícies de mesma orientação recusadas; contato planar explícito aceito |
| Cada tentativa disparava124 imagens | Perfil `quick` de16 imagens, incluindo verso/topo/base; revisão técnica e fingerprint/contexto antes da final de124 no painel para candidatos |Prévia ausente/não revista/alterada bloqueia final; fontes defeituosas podem ser diagnosticadas |
| Encerrar uma captura curta podia marcá-la completa | Contagem esperada e posição conferidas; erro de render não avança; `finish` idempotente |Interrupção, falha de render, orçamento e liberação de recursos |
| Troca sequencial podia deixar apenas parte da montagem atualizada | `ComponentBatch`: preparação/UV/auditoria de todos, guarda de edições e rollback das trocas em caso de erro |Falha simulada na segunda troca restaura ambas; teste real0/3 em processo independente |
| Translação mundial produzia duplicações/áreas nulas falsas em float32 | Métricas usam a transformação linear com origem próxima; matriz completa ainda invalida cache/edições |Microgeometria tem métricas idênticas na origem e transladada |

## Fluxo de uso

1. Medir escopo e interfaces; reutilizar somente quando os identificadores de conteúdo/configuração/dependências correspondem.
2. Gerar uma peça funcional por vez. As regiões medidas vêm da construção e da referência, não da seleção posterior dos vértices que já parecem corretos.
3. Conferir topologia, dimensões, planos/círculos declarados e interfaces específicas. Erro ou verificação incompleta impede a troca.
4. Capturar16 vistas e examinar de fato. `review_quick_capture(path, notes)` registra essa revisão técnica; não concede aprovação estética.
5. Quando estável, capturar124 vistas, usando `reviewed_preview=...` e `require_quality=True`. O painel ativa esses requisitos para candidatos. O API preserva inspeção diagnóstica de fontes com defeitos.
6. Substituir no mesmo lugar, mantendo fonte recuperável, contexto da peça e relatório. A atualização0/3 agora prepara ambas antes de trocar qualquer uma.

## O que não é comprovado

O teste por centroides detecta classes conhecidas de superfícies quase coplanares, não toda interseção possível de triângulos. Contenção, espessura mínima geral, folga de mecanismos e semelhança estética não são certificados automaticamente. Planos e círculos só são aferidos onde existem regiões/medidas explícitas. Orçamento excedido é resultado incompleto, não aprovação.

O cache de geometria não reaproveita decisões estéticas nem classificações de contato de outro modelo. As espessuras e raios da mão continuam específicos da referência. As assinaturas legadas de reparo foram mantidas; o formato rápido novo é usado no cache e no caminho de atualização em lote.

As receitas0/3 foram atualizadas. A integração de troca foi testada usando os arquivos medidos já gerados, em processo descartável; esta atualização de software não regenera nem salva a cena aberta pelo usuário.

## Evidência de desempenho

`cache-benchmark.json`: medição local dos15 componentes salvos, processo independente e sem salvar o modelo. Comparar os tempos registrados naquele arquivo; não interpretar a aceleração da reanálise como aceleração de todo o trabalho artístico. A prévia reduz124→16 imagens por tentativa; a cobertura final permanece integral. `hand-refresh-test-results.json` registra a atualização real preparada/auditada em cerca de8s e a preservação de673 outras malhas, sem salvar o arquivo aberto pelo usuário.
