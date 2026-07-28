# Backlog — o que ficou aberto e por quê

**Ler no começo de cada sessão.** Cada item nasceu de uma sprint que decidiu *não*
resolvê-lo naquele momento, e o contrato daquela sprint explica a decisão. Onde o defeito
mora no código há um comentário `BACKLOG M1.1` (ou o id correspondente) apontando para cá
— assim o problema encontra quem for mexer ali, em vez de depender de alguém lembrar de
abrir um documento.

Ordenado por gravidade, não por ordem de descoberta.

---

## ✅ Fechados

- **M1.1** — a OF passou a ser montada a partir do `CalculationSnapshot` assinado, não do
  banco vivo (`apps/production/tests_of_do_snapshot.py`). O RED mediu a diferença: a
  fábrica recebia **0,01 h** onde o engenheiro assinara **8,00 h**, e **0,001 kg** onde
  eram **730 kg**. Fallback para o banco quando a chave não existe no snapshot — sem ele,
  cotação aprovada antes do M1 deixaria de converter.
- **S3.1** — a conciliação passou a medir pelas **OFs entregues** no período
  (`OrdemFabricacao.completed_at`), não pelas cotações criadas. Antes, uma cotação criada
  em março e entregue em junho caía no balde errado e enviesava o fator nas duas pontas.
  OF ainda em produção fica de fora de propósito: aquelas horas continuam sendo gastas.
- **M1.3** — o memorial ASME agora **degrada em vez de desaparecer**. Eram três defeitos
  somados: o guard decidia "tem pressão?" por truthiness do JSON cru enquanto o construtor
  decidia por `float()` (então `"50,0"` exigia um memorial impossível de montar);
  `corrosao_mm` era o único campo guardado por `is not None`, deixando `""` chegar em
  `float("")`; e o `try` cobria o corpo inteiro, então falha numa etapa opcional tardia
  descartava um memorial essencial já pronto. Só a pressão é essencial — o resto degrada.
- **M1.2** — o admin do Django deixava `custo_*`, `preco_*`, `peso_*`, `fator_preco` e
  `impostos_pct` editáveis, e gravar por ali não emite snapshot. Custo é DERIVADO: sai do
  motor ou do roll-up, nunca da digitação. Era o último bypass conhecido do selo.
- **M1.5** — `engine_version` foi para `calc-snapshot-v2`, acompanhando o schema que o M1
  mudou. É metadado, não entra no hash, então bumpar não invalida nada.
- **M1.6** — `origem="manual"` só é marcado quando algum número mudou de fato. O
  formulário envia todos os campos, então marcar incondicionalmente carimbava linha
  intocada, mudava o hash, invalidava a assinatura e notificava sem edição nenhuma.
- **M1.4**, **M1.7** (commit `abd06ed`) · **S2.3** (commit `f1c4b37`).

---

## 🟡 Quebra ou distorce em situação real

---

## 🟢 Higiene e ruído

### M1.8 — o snapshot guarda totais com mais casas do que as colunas
`backend/apps/quotations/services.py` (`build_snapshot_payload`)

O payload é montado a partir da instância em memória logo depois do motor rodar, antes do
round-trip ao banco. Então `totals.custo_total` sai como `34344.932286` enquanto a coluna
`DecimalField(14,2)` guarda `34344.93`. O hash é do valor não arredondado.

Ninguém quebra por causa disso hoje (a conversão recarrega a OF do banco), mas significa
que o número assinado e o número persistido diferem na terceira casa. Arredondar no
payload muda todos os hashes — por isso não foi feito junto do M1.1.

### S2.1 — a tela do custo/hora dentro do produto
O formulário público (`form.qtec.me`) já coleta e o comando importa. Falta a tela
interna — que deve nascer com a pele do Vitali, não com a atual.

Contrato: `docs/discovery/SPRINT_S2_CUSTO_HORA.md` · `docs/DESIGN_IDENTIDADE_VISUAL.md`

### S3.2 — cruzar o fator da folha com a ociosidade do Nível 0
A diferença entre horas pagas e horas produtivas é a **mesma grandeza medida por dois
caminhos**: pelo S3 (conciliação) e pelo S2 (capacidade prática). Os dois números têm de
fechar — e se não fecharem, um dos dois está errado.

É provavelmente o teste mais forte que o produto pode fazer sobre si mesmo, e por isso
vale mais do que a posição na lista sugere.

---

## ⛔ Travado em decisão de terceiro

### S2.2 — ligar o custo/hora aferido ao motor
**Bloqueado na pergunta w-014** (fila em `well.qtec.me`).

O custo/hora real está calculado e **inerte**. Ligá-lo ao `TenantCostChain` reprecifica
todas as cotações do tenant de uma vez. Substituir o rate, virar piso com alerta, ou
ficar só como diagnóstico é decisão do dono da margem — não de quem escreve o código.

---

## Também esperando o Wellington (não é dívida técnica)

Ver `docs/discovery/DOMINIO_RESPOSTAS_WELLINGTON.md` §5. O que trava precisão do motor e
só ele resolve: um orçamento fechado real de designação nova, um **segundo** BEU ou BEM
(para validar em vez de só ajustar), a tabela de hora-máquina por recurso, o roteiro do
espelho e o passo praticado por bitola.
