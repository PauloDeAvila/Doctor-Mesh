# Resultado verificado — 28/10/2026

| Verificação | Resultado |
|---|---|
| Scanner e regras de aprendizado | 18 testes aprovados |
| Contratos de IA, planos e orçamento | 10 testes aprovados com cliente simulado |
| Reparos, preservação e rollback | 11 testes aprovados |
| Perfis completos e vizinhança | 7 testes aprovados |
| Captura de duas órbitas + vistas complementares | 124 imagens realmente renderizadas; configurações originais preservadas |
| Operadores registrados | Plano → prévia → aprovação → aplicar → rollback executados no Blender |
| SDK real OpenAI 3.40.0 | Contagem e Responses passaram por HTTP local simulado; importação também conferida no Blender aberto |
| Serviço OpenAI real | Não chamado; depende de chave, modelo e preços configurados |
| White Lab demonstrativo | Salvo e reaberto; Octane/Filmic/4K/PT512/três áreas preservados; nenhum render4K |
| Mecha aberto | Amostra de 20 malhas em leitura, sem erros; não é auditoria integral dos 709 objetos |
| Instalação | Habilitado e preferências salvas; 17 arquivos Python conferidos por SHA256 |
| Interface nativa | Painel aberto e desenho dos controles inspecionado na janela do Blender |

Os relatórios JSON na raiz e em `reports/` sustentam estes resultados. Estado geométrico testado não equivale a aprovação artística ou fabricação. As limitações da implementação estão descritas no README; a lista completa de capacidades avançadas do briefing permanece uma evolução incremental, não uma certificação de reconstrução universal.
