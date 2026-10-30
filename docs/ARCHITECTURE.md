# Arquitetura e decisões

Fluxo: scan → medidas → vistas → diagnóstico → plano → cópia → operação → validação → revisão → aplicação/rollback → registro.

| Módulo | Contrato |
|---|---|
| config | Tolerâncias mundiais e limites explícitos |
| identity | IDs de sessão e SHA256 de coordenadas/conectividade |
| scanner | Cena ativa, coleções, dependências, base/avaliada; sem alteração geométrica |
| dependencies/materials | RNA, vínculos, atributos, UVs e inventário; não promete avaliação estética |
| geometry | Métricas e candidatos determinísticos, com cobertura não testada explícita |
| capture | Cópias avaliadas em cena Workbench, câmera única, duas órbitas e manifestos |
| ai_client | Sem bpy; Responses com JSON Schema, ferramentas de proposta/pedido e budgets |
| planning | Alvo/base/fingerprint/região e parâmetros cadastrados; rejeita extras |
| repair | BMesh em cópia, proveniência por vértice, proteção de regiões, aplicação revisada |
| reconstruction | Perfil completo extrudado/revolvido, triangulação nativa, apoios e interfaces |
| validation | Métricas antes/depois, deslocamento, dimensões, topologia e preservação externa |
| reporting | JSON versionado, gravação atômica, status parcial/cancelado explícito |
| knowledge/policy | Casos imutáveis + aprovação separada + contratos das skills |
| ui | Timer por objeto/vista; rede em worker sem bpy; cancelamento e erros |

Decisão: as preferências de28/10substituem backups sucessivos do briefing. Originais são preservados como datablocks no mesmo projeto; não se criam arquivosBefore por operação. Uma inspeção não muda o motor atual. Projetos novos usam o White Lab; capturas diagnósticas usam outra cena e não equivalem a novos projetos de render.

Decisão: autorizações são específicas. Um plano de IA não é aprovação. Uma aprovação técnica não implica aprovação estética. Uma peça fechada não prova montagem fechada nem ausência de colisão. Observações não fundamentadas permanecem pendentes.

Decisão: não depender de scripts históricos de cenas como bibliotecas. Foram consultados a arquitetura `mecha_asset_pipeline/ESCOPO_E_ARQUITETURA.md`, o BIS e as skills locais; implementação própria modular com testes sintéticos. Preferências e receitas históricas são fontes, não parâmetros universais.

Decisão: API é substituível por um cliente injetado; nenhum código de reparo aceita texto executável. SDK3.40.0 foi testado com MockTransport real. Chave/modelo e qualidade do serviço real permanecem não validados.

Decisão: validação automática conserva fronteiras e feições mecânicas; reconstruções de superfície livre ou fechamento semanticamente ambíguo devem parar e pedir medidas. Não há promessa universal de precisãoCAD, produção industrial, rig ou exportação game-ready.
