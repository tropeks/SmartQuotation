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
- **M1.4**, **M1.7** (commit `abd06ed`) · **S2.3** (commit `f1c4b37`).

---

## 🟡 Quebra ou distorce em situação real

### S3.1 — a conciliação usa a data errada
`backend/apps/cost_discovery/management/commands/conciliar_horas.py`

O período filtra por `Quotation.created_at`, mas a pergunta certa é *"quais OFs foram
ENTREGUES neste período"* — é contra elas que as horas da folha foram gastas. Uma cotação
criada em março e entregue em junho entra no balde errado, e o fator sai enviesado.

Depende de a OF ter data de conclusão confiável: verificar `apps/production` antes.

Contrato: `docs/discovery/SPRINT_S3_ANCORA_FOLHA.md`

### M1.3 — permutador pressurizado sem memorial dá 500 na EAP
`backend/apps/quotations/services.py:77`

`build_snapshot_payload` levanta `RuntimeError` quando o escopo é `complete` com
`pressao_projeto_bar` e o memorial ASME não monta. Como o M1 passou a emitir snapshot em
toda edição da EAP, essa classe de cotação agora **quebra ao editar** — caminho que
funcionava antes, porque antes o override não construía snapshot nenhum.

Fail-closed (a transação reverte, nada é gravado), então não é bypass. Mas inutiliza o
drawer para permutador pressurizado.

Contrato: `docs/discovery/SPRINT_M1_FURO_EAP.md`

### M1.2 — o admin do Django edita custo sem selo
`backend/apps/quotations/admin.py:11-21`

`QuotationAdmin` não declara `fields` nem `exclude`, então `custo_material`, `custo_mo`,
`custo_total`, `fator_preco` e `impostos_pct` ficam editáveis no formulário, sem emitir
snapshot. Esses campos alimentam direto o cabeçalho da OF.

Exige `is_staff` — flag do Django, não concedida por papel de tenant — então é caminho de
staff de plataforma, não escalada de papel. Ainda assim é bypass vivo do selo. Correção:
`readonly_fields` nos campos de custo.

---

## 🟢 Higiene e ruído

### M1.5 — `engine_version` não acompanha o schema do payload
`backend/apps/quotations/services.py:17`

O payload de `operacoes` ganhou horas, taxas, `custo_direto` e `origem` no M1, mas
snapshots antigos e novos continuam identificados como `calc-snapshot-v1`. Quem for
comparar snapshots de épocas diferentes não tem como saber que o formato mudou.

### M1.8 — o snapshot guarda totais com mais casas do que as colunas
`backend/apps/quotations/services.py` (`build_snapshot_payload`)

O payload é montado a partir da instância em memória logo depois do motor rodar, antes do
round-trip ao banco. Então `totals.custo_total` sai como `34344.932286` enquanto a coluna
`DecimalField(14,2)` guarda `34344.93`. O hash é do valor não arredondado.

Ninguém quebra por causa disso hoje (a conversão recarrega a OF do banco), mas significa
que o número assinado e o número persistido diferem na terceira casa. Arredondar no
payload muda todos os hashes — por isso não foi feito junto do M1.1.

### M1.6 — `origem="manual"` é marcado sem mudança real
`backend/apps/quotations/views.py` (bloco de operação horária em `eap_item_save`)

O formulário envia todos os campos, então qualquer POST marca todas as operações
horárias como `manual`, mesmo quando nenhum número mudou. Isso muda o hash, invalida a
assinatura e notifica sem edição material. Só marcar quando o valor de fato mudou.

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
