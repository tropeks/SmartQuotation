# PROJECT_BRIEF.md — SmartQuotation

> **Status:** Aprovado para desenvolvimento | **Versão:** 1.0 | **Data:** 2025

---

## 1. Declaração do Problema

Fabricantes brasileiros de equipamentos sob pressão e caldeiraria pesada (vasos de pressão,
trocadores de calor, tanques, reatores) de pequeno e médio porte dependem hoje de processos
manuais — planilhas Excel, e-mails e ferramentas genéricas — para elaborar cotações
técnico-comerciais. Esse processo é lento, propenso a erros, não rastreável, e desconectado
das etapas seguintes de fabricação (BOM, roteiro, PCP, qualidade).

Softwares especializados de cálculo de vasos sob pressão (PVElite, Compress) são caros e
inacessíveis para PMEs. ERPs industriais (TOTVS Protheus, SAP B1) não cobrem adequadamente
o domínio de cotação técnica de equipamentos sob encomenda.

**SmartQuotation** resolve esse problema entregando uma plataforma SaaS multi-tenant que
automatiza o dimensionamento normativo (ASME/TEMA), forma o preço de venda e gera a proposta
comercial — e quando a cotação se converte em pedido, reutiliza todos os dados para alimentar
BOM, roteiro de fabricação e integrações com ERP.

---

## 2. Visão do Produto

> "Ser a plataforma de referência para cotação técnico-comercial e gestão da produção de
> equipamentos sob encomenda da indústria de caldeiraria brasileira de pequeno e médio porte —
> acessível, confiável e normativamente correto."

### Proposta de Valor Central

| Para quem | O que entrega | Diferencial |
|---|---|---|
| Orçamentista / Engenheiro | Cotação técnica completa em horas, não dias | Dimensionamento ASME/TEMA automatizado validado contra PVElite |
| Gestor Comercial | Formação de preço padronizada com margem controlada | Rastreabilidade total da proposta ao pedido |
| PCP / Produção | BOM e roteiro prontos no momento do pedido | Zero retrabalho de digitação |
| Direção | Visão de rentabilidade por cotação e por pedido | KPIs integrados de cotação→produção |
| Mercado (SaaS) | Alternativa acessível ao PVElite/Compress | Preço SaaS mensal vs. licença cara |

---

## 3. Horizontes de Desenvolvimento

### H1 — Motor de Cotação (MVP, 0–6 meses)

**Escopo:**
- Cadastro de tenant (empresa), usuários e perfis RBAC
- Cadastro de materiais com propriedades físicas e preço de mercado
- Cadastro de operações, máquinas, centros de custo e índices de produtividade
- Dimensionamento normativo automático:
  - Vasos de pressão: ASME VIII Div.1 (UG-27, UG-32, UG-37)
  - Trocadores de calor: TEMA (tipos E, F, G, H, J, X, K)
- Decomposição paramétrica em componentes tipados (casco, tampos, bocais, flanges, espelhos, feixe tubular, chicanas, selas/pés)
- Dois modos de cálculo por componente: **Calculado** (sistema) e **Importado** (cliente/terceiro)
- Assinatura eletrônica do responsável técnico (CREA + ART)
- Formação de preço: custo material + mão-de-obra + overhead + impostos + margem
- Geração de proposta em DOCX e PDF com template customizável por tenant
- Histórico de cotações com versionamento
- Multi-tenant com isolamento físico de dados (schema-per-tenant)
- Audit trail completo (quem, o quê, quando)

**Fora do escopo do H1:**
- Conversão cotação→pedido (ordem de fabricação)
- BOM e roteiro de fabricação formal
- Integração com ERPs externos
- Tanques API 650 / tubulações B31.x
- App mobile
- Portal do cliente

---

### H2 — Gestão da Produção (6–18 meses)

- Conversão de cotação aprovada em Ordem de Fabricação (OF)
- BOM multi-nível herdado da cotação (zero retrabalho)
- Roteiro de fabricação herdado da cotação
- Captura de tempos reais por operação (apontamento)
- Motor de aprendizado de índices: Industry Standard → Tenant → Actual
- ITP (Inspeção e Teste) básico
- Integrações ERP via conectores plugáveis:
  - Fase 2a: TOTVS Protheus e Omie
  - Fase 2b: SAP B1 e Sankhya
  - Export/Import CSV/JSON padronizado como fallback universal
- Expansão normativa: Tanques API 650/620, Tubulações ASME B31.1/B31.3, Silos, Estruturas metálicas pesadas

---

### H3 — ERP Especializado (18m+)

- PCP completo (programação de produção, kanban de OF)
- Apontamento de chão de fábrica (MES)
- Gestão de qualidade integrada (NC, AC, AP, ITP completo)
- NF-e / NFS-e integradas
- Portal do cliente (acompanhamento de pedido, aprovação de documentos)
- BI e dashboards executivos
- App mobile para apontamento

---

## 4. Stakeholders

| Papel | Responsabilidade |
|---|---|
| Product Owner (Romulo) | Visão de produto, priorização, aceite de entrega |
| Engenheiro de Domínio (irmão do P.O.) | Especificação e validação das fórmulas normativas (ASME/TEMA), validação contra PVElite |
| Dev Parceiro | Implementação backend/frontend com supervisão do P.O. |
| Clientes Piloto H1 | Fabricantes de caldeiraria PME, 1–3 empresas, pilotos não-pagos |
| Usuário Final: Orçamentista | Usa o sistema diariamente para elaborar cotações |
| Usuário Final: Engenheiro | Valida/assina cálculos normativos |
| Usuário Final: Gestor Comercial | Analisa rentabilidade, aprova propostas |

---

## 5. Premissas

1. O módulo de cálculo normativo é o núcleo comercial do produto; sua precisão é não-negociável.
2. Validação cruzada contra PVElite (acesso disponível) é gate obrigatório de release do motor de cálculo.
3. A empresa que usa o sistema assume responsabilidade técnica via engenheiro habilitado (ART/CREA).
4. O modelo de dados é desenhado para multi-tenant desde o Sprint 0 — refactor futuro é inaceitável.
5. Dados de cotações e cálculos têm retenção mínima de 15 anos (NR-13).
6. Stack tecnológica definida nas ADRs (ver ARCHITECTURE.md) é o baseline; mudanças exigem nova ADR.
7. Clientes-alvo são PMEs brasileiras — UX deve priorizar clareza sobre sofisticação visual.

---

## 6. Restrições

| Tipo | Restrição |
|---|---|
| Prazo | MVP (H1) em 90 dias (~6 sprints de 2 semanas) |
| Time | P.O. + 1 dev parceiro; eng. de domínio em consultoria parcial |
| Infraestrutura | VPS em região Brasil (soberania de dados); sem lock-in em cloud proprietária |
| Regulatório | Conformidade com NR-13, ASME VIII, TEMA, LGPD, caminho para ISO 9001 e 27001 |
| Idioma | Produto em Português (BR); código, APIs e comentários em Inglês |
| Budget | MVP bootstrap; sem gasto com licenças de software (100% open-source) |

---

## 7. Conformidade e Regulamentação

| Norma/Regulação | Aplicação |
|---|---|
| **NR-13** (MTE) | Rastreabilidade de projeto, prontuário, responsável técnico, histórico de inspeções |
| **ASME BPVC Sec. VIII Div.1/Div.2** | Código construtivo de vasos sob pressão — base do motor de cálculo |
| **TEMA** | Padrões para trocadores de calor — base do motor de cálculo |
| **API 650/620** | Tanques atmosféricos — H2 |
| **ASME B31.1 / B31.3** | Tubulações — H2 |
| **PED 2014/68/EU** | Diretiva de equipamentos sob pressão (UE) — clientes exportadores |
| **LGPD** | Dados pessoais de clientes e usuários; base legal "execução de contrato" |
| **ISO 9001** | Rastreabilidade cotação→pedido, controle de documentos, ações corretivas |
| **ISO/IEC 27001** | Segurança da informação — alvo de médio prazo para credenciamento SaaS |

---

## 8. Glossário do Domínio

| Termo | Definição |
|---|---|
| **Vaso de Pressão** | Recipiente fechado sujeito à pressão interna ou externa, projetado conforme ASME VIII |
| **Trocador de Calor** | Equipamento para transferência de calor entre dois fluidos, projetado conforme TEMA |
| **Casco** | Corpo cilíndrico principal do equipamento |
| **Tampo** | Fechamento das extremidades do casco (toriesférico, elíptico, hemisférico, cônico, plano) |
| **Bocal** | Conexão tubular para entrada/saída de fluidos ou instrumentação |
| **Flange** | Elemento de conexão entre bocal e tubulação ou tampa |
| **Espelho (Tubesheet)** | Placa perfurada que separa o lado casco do lado tubo nos trocadores |
| **Feixe Tubular** | Conjunto de tubos internos do trocador de calor |
| **Chicana (Baffle)** | Defletor interno para direcionar o fluxo no lado casco |
| **PWHT** | Post Weld Heat Treatment — tratamento térmico pós-solda |
| **RX / END** | Ensaio não-destrutivo por radiografia |
| **ITP** | Inspection and Test Plan — plano de inspeção e teste |
| **ART** | Anotação de Responsabilidade Técnica (CONFEA/CREA) |
| **MAWP** | Maximum Allowable Working Pressure — pressão máxima de trabalho admissível |
| **MRR** | Material Removal Rate — taxa de remoção de material (usinagem) |
| **OF** | Ordem de Fabricação |
| **BOM** | Bill of Materials — lista de materiais |
| **Sobremetal** | Corrosion allowance — espessura adicional por corrosão prevista |
| **Kerf** | Largura do corte (laser/plasma) — afeta aproveitamento de chapa |
| **Tenant** | Empresa cliente no modelo SaaS multi-tenant |
| **Job Shop** | Fábrica de produtos sob encomenda, sem produção em série |
| **PME** | Pequena e Média Empresa |
