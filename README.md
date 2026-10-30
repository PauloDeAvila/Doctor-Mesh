# Blender AI Mesh Doctor 0.2

## Atualização de desempenho e qualidade

- Leitura única de NPZ com limites e validação de índices/números; conferência da fonte antes de reutilizar perfis.
- Cache persistente por conteúdo, matriz, configuração, unidades e versão. Base e avaliada idênticas compartilham análise; resultados parciais não são reutilizados.
- Prévia rápida padrão de16 imagens; inspeção final mantém124. No painel, candidatos precisam da prévia conferida da mesma geometria/contexto e do teste geométrico antes da final. Inspeções de fontes defeituosas continuam permitidas.
- Captura parcial nunca recebe estado completo. Falha de render não avança a fila. Limpeza é idempotente; limite de tempo é verificado entre quadros.
- Verificação de planos/círculos medidos e faces quase coincidentes; cortes passantes excedem as duas extremidades do material. Contatos opostos exigem um plano explícito; paredes cilíndricas de mesma orientação sobrepostas são sinalizadas.
- Substituição em lote: preparar/verificar tudo antes de alterar fontes, recuperar a versão anterior se uma troca falhar e preservar edições feitas durante a preparação.
- Medições com origem local evitam falsas degenerações de float32 causadas pela posição do objeto no cenário. Formatos antigos de assinatura de rollback foram preservados.

Detalhes e limites: `docs/FAILURES_AND_GATES.md`. Evidências: `efficiency-test-results.json`, `cache-benchmark.json`, `hand-refresh-test-results.json`. Nenhuma verificação automática garante perfeição estética, ausência geral de auto-interseções ou tolerância industrial.

Projeto funcional de inspeção e reparo medido para Blender. Implementado e testado no **Blender 5.4.0 Alpha b1d561a6c0d6 / Python 3.13.13 / Windows**, em 28/10/2026. Esta versão prioriza diagnóstico determinístico, operações limitadas e evidências; reconstrução livre de qualquer modelo continua fora do escopo comprovado.

## Entregas

- `dist/ai_mesh_doctor-0.2.0.zip`: add-on instalável, sem chave de API.
- `project/AI_Mesh_Doctor_Demo.blend`: projeto independente baseado no White Lab do usuário, com três casos didáticos. Preserva Octane, Filmic, PNG16, 3840×2160, kernel ativo PT512/preview32, três áreas e câmera sem DOF. Não foi iniciado render4K.
- `scripts/scan_project.py`: inspeção por linha de comando, sem salvar alterações no `.blend`.
- `examples/`: relatórios reais dos testes, manifesto de skills, especificação medida e reconstrução.
- `reports/live-scene-sample.json`: amostra de 20 malhas visíveis do mecha aberto; leitura apenas, não auditoria integral dos 709 objetos.
- `tests/`, `*-test-results.json`: testes e evidências executadas. O arquivo `test-results.json` contém os 18 testes do scanner.

## Instalação e uso

O pacote é um add-on Python tradicional. No Blender: Preferences → Add-ons → Install from Disk, escolher o ZIP e habilitar **AI Mesh Doctor**. Abra a aba **AI Mesh Doctor** na barra lateral N da janela3D. O add-on também pode ser instalado por `bpy.ops.preferences.addon_install(filepath=...)` e `bpy.ops.preferences.addon_enable(module='ai_mesh_doctor')`.

1. Trabalhar em Object Mode. Usar Scan Entire Project para a **cena ativa**, ou Scan Selected Objects para a seleção. Cenas adicionais devem ser inspecionadas separadamente.
2. Ler o JSON indicado em Last JSON. Status `partial`/`cancelled`/`skipped_limit` nunca significa aprovação. O botão principal usa um timer, processa um objeto por passo e permite Esc entre objetos. Um objeto individual ainda pode ocupar a thread principal até terminar sua etapa.
3. Para documentação visual, selecionar uma peça, usar Quick preview (16 vistas), conferir as imagens e registrar notas em Record Quick Preview Review. Quando o candidato estiver estável, escolher Final360 e Capture Selected Inspection:124vistas (6eixos+24horizontal+24vertical+8diagonais, isolada e montada). A câmera é reutilizada em cena temporária. Workbench é uma modalidade diagnóstica neutra; não muda Octane/White Lab do projeto. O modo wireframe usa Wireframe em cópias, não material final. Vistas internas/ocluídas exigem inspeção complementar; não existe promessa de visibilidade universal.
4. Para reparar, escolher operação e região em índices da **malha base**, ou marcar explicitamente Use whole active component. Configurar limites de deslocamento, dimensões e mudanças topológicas. Generate Measured Repair Plan cria um JSON e um texto `MD_Plan.json`. Índices de uma malha avaliada nunca são aceitos como índices da base.
5. Preview Repair cria uma cópia e valida antes de exibi-la. A fonte é preservada. Revisar a prévia e só então marcar aprovação e aplicar. Discard Preview restaura a visibilidade original. Rollback Last Repair recupera o datablock original no mesmo projeto; recusa sobrescrever edições posteriores não registradas.
6. Para reconstruir, preencher a especificação medida em `examples/housing-specification.json`, selecionar a fonte e criar a prévia. O gerador oferece perfil extrudado completo e perfil de revolução fechado. Não infere uma família arbitrariamente a partir de uma malha deformada.
7. A aceitação da reconstrução exige medidas compatíveis, interfaces/contatos classificados, manifestações antes/depois do alvo com órbitas completas e aprovação visual explícita. A nova peça permanece separada; a fonte fica oculta no mesmo projeto. Reexibir a fonte e ocultar a nova peça reverte a apresentação. UVs/materialmapping da substituição precisam de revisão explícita; não são reconstruídos automaticamente.

Não editar, renomear ou remover datablocks envolvidos enquanto houver uma prévia ativa. Após reiniciar o Blender ou usar undo externo, descartar a prévia antiga e gerar outra com novo scan. Não existe retomada automática de uma transação de prévia após reinício. A fonte e o histórico aplicado ficam no `.blend` quando ele é salvo.

## O que é medido

Hierarquia recursiva de coleções, objetos, matrizes, bounds mundiais, escala/determinante, visibilidade, edição, datablocks compartilhados, instâncias avaliadas, pais/filhos, modificadores RNA, constraints, drivers, materiais, UVs, atributos, custom normals e shape keys. O relatório descreve a base e a geometria avaliada separadamente e libera todas as cópias avaliadas.

Na geometria: contagens, distribuição de polígonos, comprimentos/áreas em espaço mundial, ilhas conectadas, bordas abertas e radiais, vértices não manifold, geometria solta, faces degeneradas, arestas curtas, pares próximos por KDTree, winding inconsistente, volume assinado por ilha fechada, planicidade de n-gons, proporção entre arestas e ângulos diedros. Proximidade não prova duplicação acidental. Volume negativo também pode representar uma cavidade ou transformação espelhada. Arestas sharp são descritas, não removidas.

IDs são estáveis durante a sessão e não gravam propriedades nos objetos inspecionados. Não são IDs globais permanentes. Fingerprints invalidam planos após mudança de topologia/coordenadas. A validação de aplicação também confere atributos, UVs, materiais, transformações, hierarquia, modificadores e constraints contra a prévia. O cache0.2 persiste por conteúdo/configuração/matriz/unidades/versão, inclui geometria avaliada e não usa ponteiros temporários como identidade. Reuse unchanged measurements controla esse reaproveitamento no painel; materiais/UV são inspecionados novamente.

## Sem remendos arbitrários

Não existe operação genérica `fill holes`, `make manifold`, remesh global ou execução de Python da IA. Um contorno aberto tem intenção `unknown` até interpretação do desenho. O gerador constrói o **volume inteiro** a partir de um perfil simples, rejeita cruzamentos e confere bounds independentes, manifold, winding, volume e apoios. Um alojamento anular possui parede interna, externa e retornos conectados; seu furo funcional não precisa de bordas topológicas abertas.

Operações disponíveis: normais, merge local com tolerância, remoção de geometria solta, projeção parcial num plano medido por mínimos quadrados, suavização local com bordas/feições fixas e relaxamento tangencial. O alvo deve melhorar sua métrica; peças limpas são recusadas em operações sem benefício. Limites protegem geometria externa à região. Custom split normals, shape keys, Multires e Geometry Nodes que precisem de um fluxo específico bloqueiam reparo automático nesta versão.

Testes de vizinhança combinam AABB, sobreposição de triângulos e amostras de contenção em três direções. AABB disjunta prova separação; proximidade sem interseção provada permanece pendente. Interpretações `intentional_contact`, `intentional_overlap` e `clearance_reviewed` são decisões registradas do responsável. Não há certificação de folga mínima, contenção completa em malhas abertas, colisão durante movimento ou fabricação.

## OpenAI opcional

A camada segue a documentação oficial de [Responses](https://developers.openai.com/api/reference/python/resources/responses), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Function Calling](https://developers.openai.com/api/docs/guides/function-calling) e [contagem de tokens](https://developers.openai.com/api/docs/guides/token-counting). O SDK **openai3.40.0** foi instalado em diretório isolado do Mesh Doctor no Blender5.4 e testado com seu cliente real em transporte HTTP simulado local. **Nenhuma chamada real ao serviço foi feita.**

Configure o modelo exato disponível na sua conta e `OPENAI_API_KEY` no ambiente antes de iniciar o Blender. Nenhuma chave é salva no código, relatório ou `.blend`. A instalação local do SDK está em `%APPDATA%/Blender Foundation/Blender/5.4/datafiles/mesh_doctor/python`; o adaptador CLI também aceita `MESH_DOCTOR_PYTHON_DEPS`. Em outra máquina, instalar `requirements-ai.txt` com o Python correspondente ao Blender em um diretório isolado e apontá-lo por essa variável. Falta do SDK não impede scanner/reparo local.

Habilitar envio explicitamente no painel. Fornecer preços verificados por1milhão de tokens e orçamento máximo por diagnóstico. O cliente consulta a contagem multimodal, reserva saída máxima e margem para schema, e bloqueia a geração que exceda a estimativa. Não é um teto de faturamento da conta: depende dos preços informados; outras aplicações e cliques posteriores têm orçamentos próprios. Limites adicionais:1geração por diagnóstico,8imagens,100KB de texto,8MB de imagem,2048tokens de saída,45s por pedido e zero retries automáticos. Cancelar descarta a resposta; um pedido já enviado pode ser cobrado.

Os estágios overview/component/region/planning são escolhidos pelo usuário; não há loop de reconstrução autônoma. O resumo inclui evidências geométricas, imagens/referências escolhidas e as regras de construção. A IA pode pedir mais evidência ou **propor** somente uma operação cadastrada para alvo/região/fingerprint existentes. Chamadas de ferramentas desconhecidas e respostas inválidas são recusadas. Nenhuma proposta é executada automaticamente. Diagnóstico e planos ficam em JSON, com uso de tokens quando fornecido pelo serviço.

## Skills e aprendizado reutilizável

`policy.py` integra mecha-design, anatomy, optics, eyes, interfaces, multiview, refactory local, reconstrução dimensional e hard-surface com caminhos e hashes das fontes locais. O protocolo360 vigente tem prioridade: entender montagem e partes, medir interfaces antes de gerar, reunir fragmentos da mesma peça funcional e preservar divisões de função real. As medidas dos olhos antigos não são transportadas para outras peças. Manifesto das skills: `examples/skill_manifest.json`.

O SQLite em `%APPDATA%/.../datafiles/mesh_doctor/knowledge.sqlite3` guarda casos imutáveis, fontes, unidades, medidas, método, parâmetros, erros, correções, evidências, testes, limites, regra reutilizável e estado de aprovação. Scans e reparos feitos pelo painel geram registros automaticamente. Registros automáticos **não têm intervalo de reutilização**, pois uma execução isolada não prova generalização.

Para consolidar uma receita, criar `MD_Case.json` no Text Editor conforme `examples/case-template.json`, declarar família, unidades e intervalos dimensionais justificados, registrar testes e aprovação reais. Record Case acrescenta uma revisão, sem apagar falhas antigas. Retrieve Compatible Approved Recipes retorna somente casos tested+approved na mesma família/unidade e dentro dos intervalos. Sempre exige nova validação. Não é treinamento de modelo nem garantia de reconstrução mais precisa sem novos dados.

Capturas possuem manifesto de propriedade. Após conclusão e aprovação do escopo, Clean Approved Temporary Captures remove somente os PNGs daquela pasta identificada, mantendo medidas e o manifesto. Referências e renders finais não entram nessa limpeza. A câmera interna de captura é um recurso temporário que é liberado ao terminar a operação e nunca é salva na cena do usuário.

## Testes reproduzíveis

No PowerShell, a partir da raiz deste projeto:

```powershell
./scripts/run_tests.ps1 -Blender 'C:/caminho/blender.exe'
```

O runner executa nove suítes em processos Blender separados, produzindo logs em `tests/`. A última (`test_sdk.py`) requer o SDK instalado e usa HTTP local simulado. Em outra máquina sem o SDK, as demais continuam independentes dele. `scripts/build_demo.py` requer o White Lab e o Octane instalados no ambiente do usuário; não usar factory-startup nesse script. As dependências e preferências de outros add-ons podem emitir avisos no encerramento do processo; exit code e relatórios do projeto registram o resultado próprio.

Scanner por linha de comando:

```powershell
& 'C:/caminho/blender.exe' --background 'C:/modelo.blend' --python-exit-code 1 --python ./scripts/scan_project.py -- --output 'C:/relatorio.json' --max-seconds 120
```

## Limites desta versão e evolução

O Milestone1 da especificação foi implementado primeiro e validado antes das extensões. Foram adicionados os fluxos básicos de captura, API, reparo e reconstrução de famílias calculáveis. Isso **não equivale à implementação integral de todas as funções avançadas** do briefing: faltam detecção geral robusta de auto-interseções, simetria semântica e cilindros deformados, avaliação quantitativa de referência/silhueta, análise de texturas/bake, captura de materiais finais, reconstrução de superfície livre e patches locais com conectividade garantida, medição exata de clearance, coordenação automática dos quatro estágios da IA e ensaio real com serviço/modelo configurado. Não há preenchimento provisório dessas capacidades.

O próximo trabalho deve escolher uma peça real e uma família sustentada por suas medidas, registrar o caso completo e expandir somente após validar os resultados. O mecha aberto não foi reconstruído ou corrigido por esta instalação.
