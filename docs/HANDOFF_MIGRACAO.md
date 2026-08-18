# Handoff — migração do `/home/rcosta00/dev` (2026-08-18)

Estado do repositório no momento em que a área de disco foi migrada, e o que precisa de
atenção **depois** que o diretório mudar de lugar.

---

## 1. Estado: limpo e retomável

| Item | Estado |
|---|---|
| Branch | `main`, em sincronia com `origin/main` |
| Working tree | limpo (0 arquivos sujos) |
| Commits não pushados | nenhum |
| Último commit | `d1df930` — checkpoint pré-migração do Capitão |
| PRs abertos | nenhum (#111 e #112 mergeados) |

### Checks executados nesta sessão (todos verdes)

```
python -m tests.validate_feixe_completo        GATE OK — Δ −2,9% (tolerância ±10%)
python -m tests.validate_permutador_completo   GATE OK — BEU Δ 0,00% · OF3683 Δ +0,15%
python -m tests.test_solda_fisica              GATE OK
python -m tests.test_cost_chain_knobs          GATE OK
manage.py check                                sem problemas
manage.py makemigrations --check               No changes detected
```

**A suíte Django completa (~48 min) NÃO foi rodada, de propósito.** A árvore é idêntica à que
o CI validou no PR #112, mais o `d1df930`, que tocou apenas `CLAUDE.md` e dois `manifest.json`
— nenhuma linha de código. Rodar 48 minutos para reconfirmar um verde do CI não agrega. Se
quiser a confirmação assim mesmo:

```bash
cd backend && . .venv/bin/activate
POSTGRES_PORT=5436 POSTGRES_HOST=localhost POSTGRES_USER=sq POSTGRES_PASSWORD=sq \
  POSTGRES_DB=sq_p2 python manage.py test apps
```

---

## 2. ⚠️ O que quebra com a mudança de caminho — e como consertar

### 2.1 Quatro worktrees do looper apontam para este `.git`

```
~/.looper/worktrees/repo-ae42.../smartquotation/looper-fix-smartquotation-pr-{52,56,61,112}-detached
```

Eles vivem **fora** de `~/dev` (não migram junto), mas o arquivo `.git` de cada um aponta para
`/home/rcosta00/dev/SmartQuotation/.git/worktrees/<nome>`, e a metadata deste repositório
aponta de volta para os caminhos em `~/.looper`. **Mover o repositório quebra os dois lados.**

Verificado antes da migração: os quatro estão **limpos** (0 arquivos modificados) e todos os
PRs correspondentes estão **MERGED** (#52, #56, #61, #112). O que eles guardam é histórico
pré-squash — nada de único se perde.

**Conserto depois do move**, de dentro do repositório no caminho novo:

```bash
git worktree repair                      # reconecta os dois lados
# ou, se não forem mais úteis (é o caso — todos os PRs estão fechados):
git worktree list --porcelain | grep '^worktree.*looper' | cut -d' ' -f2 \
  | xargs -r -n1 git worktree remove --force
git worktree prune
```

### 2.2 Containers Docker com bind mount em `~/dev`

Sete containers montam caminhos dentro de `~/dev` — **nenhum é do SmartQuotation**, mas todos
quebram se o diretório sair debaixo deles em execução:

```
vitali-staging-nginx-1   vitali-staging-orthanc-1   vitali-staging-postgres-1
vitali-staging-db-backup-1   vitali-postgres-1   vitali-nginx-1
qm-sbx-group-web-project-a1dcae60-…
```

**Pare esses containers antes do move.** Um Postgres com o `PGDATA` puxado debaixo dele em
execução é exatamente a receita do incidente de corrupção de catálogo de 2026-07-18
(ver a memória `prod-db-catalog-corruption-2026-07-18`).

O SmartQuotation em produção (`sq-web-proto`, `sq-prod-db`, `sq-prod-redis`) usa **volumes
nomeados**, não bind mounts em `~/dev` — não é afetado pela migração.

### 2.2b ⚠️ Sessão viva segurando `~/dev/NetForge` (verificado 2026-08-18, 07:0x)

```
PID 4128486   /home/rcosta00/dev/NetForge/.venv/bin/python manage.py runserver 127.0.0.1:8011
```

O `cwd` deste processo é **`/home/rcosta00/dev/NetForge`** — ele segura o diretório do host
diretamente (confirmado por `readlink /proc/<pid>/cwd`, sem cgroup de container). É um servidor
de dev subido por **outra sessão do Claude Code** (`-home-rcosta00-dev-NetForge`), viva no
momento desta verificação.

**Não matei o processo de propósito:** é trabalho em voo de outro contexto, e derrubá-lo sem o
dono saber trocaria um risco por outro. **Encerre aquela sessão antes do move.**

Para reconferir na hora da migração — só o que segura o host aparece:

```bash
for p in $(pgrep -f "manage.py runserver"); do
  cg=$(sudo cat /proc/$p/cgroup 2>/dev/null | grep -c docker)
  [ "$cg" -eq 0 ] && echo "HOST  $p  $(sudo readlink /proc/$p/cwd)"
done
```

*(Nota: dois `runserver` na porta 8000 com 27 dias de uptime aparecem no `ps` mas rodam
**dentro** de container — `cwd=/app` — e não seguram `~/dev`. Ignorar.)*

### 2.3 Virtualenv com caminhos absolutos

`backend/.venv/bin/*` tem shebangs com o caminho absoluto antigo. Depois do move:

```bash
cd backend && rm -rf .venv && python3 -m venv .venv \
  && . .venv/bin/activate && pip install -r requirements/development.txt
```

Recriar é mais rápido e confiável que remendar shebangs.

### 2.4 Artefatos visuais fora do git

`docs/visual/{antes,depois}/*.png` estão no `.gitignore` (são artefato de verificação, não
fonte). Os `manifest.json` **estão** versionados no `d1df930`. Se os PNGs se perderem no move,
regenere:

```bash
backend/.venv/bin/python scripts/visual_baseline.py docs/visual/depois \
  --chromium-bin /usr/bin/chromium
```

⚠️ **Gotcha do harness:** esta máquina não resolve `*.localhost`. O script já contorna
(sonda no loopback com `Host` na mão + `--host-resolver-rules` no Chromium), mas se ele for
copiado para outro lugar, essa é a parte que costuma quebrar primeiro.

---

## 3. Repositórios que estavam sem cópia fora da máquina — resolvido

`sq-form` e `sq-well` (que servem **form.qtec.me** e **well.qtec.me**, ambos no ar) existiam
**apenas neste disco**, sem remote nenhum. Uma migração malsucedida levaria o fonte junto.

Resolvido em duas camadas nesta sessão:

1. **Bundles** em `~/backups/repos-sem-remote/` — verificados por restauração real, não por
   código de saída (8 arquivos voltaram no teste de clone).
2. **Remotes privados criados e pushados**: `tropeks/sq-form` e `tropeks/sq-well`.

Os bundles ficam **fora** de `~/dev`, então sobrevivem à migração de qualquer jeito.

---

## 4. Estado do produto — onde a coisa parou

**Em produção** (`quotation.qtec.me`, deploy manual de 2026-07-28, imagem `smartquotation:proto`):
vazamento de margem fechado (M1), as duas réguas de custo, e a identidade **Prancha** com
carimbo, selo divergente e proveniência na EAP.

**Não há deploy automático.** `.github/workflows/` só tem `ci.yml`; merge em `main` não sobe
nada. Procedimento completo na memória `deploy-prod-gotchas`, incluindo o gotcha do backup
vazio (`pg_dumpall` na porta errada gera arquivo de 20 bytes com exit 0 — validar por
conteúdo, nunca por exit code).

Rollback disponível: imagem `smartquotation:rollback-20260718` e dump verificado em
`~/backups/sq/pre_prancha_20260728_143633.sql.gz`.

### O gargalo não é código

**Wellington tem 14 perguntas sem resposta** em `well.qtec.me`. O custo por capacidade
(`apps/cost_structure`) está deployado e **inerte** esperando a w-014. O motor segue com **um
caso de validação por designação TEMA**.

### Próximo passo de maior valor, e é barato

Uma **varredura de sensibilidade** sobre o motor (que é Python puro, então perturbar entradas
e re-rodar custa milissegundos) para descobrir **quais campos do formulário merecem a paciência
do Wellington**. Discussão registrada na sessão de 2026-07-31; o essencial:

- MO é **32%** do custo no BEU (R$ 40.990 de R$ 128.160) — erro de 10% na capacidade prática
  move o preço final ~3,2%, não 10%. A fatia de material amortece.
- **O back-solve mascara erro de formulário**: o que a calibração fixa é o produto
  `custo_hora × fator_correcao_mo`, não cada fator. Erro na capacidade é reabsorvido, e a
  cotação calibrada sai idêntica.
- O que os campos do formulário realmente movem é o **diagnóstico** (`cost_structure.diagnosticar`:
  cada hora vendida ganha ou perde dinheiro?) e cotações **fora do ponto calibrado**.

### Itens abertos declarados no PR #112

- Fonte do PDF da proposta: o container tem só DejaVu instalada, então o `Archivo` declarado
  **nunca renderizou**. Declaração já corrigida para IBM Plex; instalar a fonte na imagem é
  mudança à parte (`fonts-ibm-plex` não existe no repo Debian da base, e este repositório pina
  dependência por hash de propósito).
- Carimbo de cotação de **feixe** fica ralo: 5 de 9 células com `—`, porque metade dos campos
  só existe em permutador completo. Decisão de produto pendente.
- `audit.approvals._technical_satisfied` é privada e virou dependência da view de detalhe —
  há `TODO` para promovê-la a API pública de `audit`.
- `scripts/backup_db.sh` **não funciona em produção**: assume `docker compose`, mas a produção
  roda em container avulso.

---

## 5. Outros repositórios em `~/dev` — fora deste ciclo

Levantados para a migração não ter surpresa. **Nenhum tem commit não pushado**, então o risco
de perda é baixo. O que existe é trabalho em andamento não versionado:

| Repo | Branch | Não rastreados | Modificados |
|---|---|---|---|
| vitali | `onda0-perimetro-multitenant` | 753 | 275 |
| NetForge | `hotfix/w0.0-containment` | 4 | 8 |
| claudeproxy | `master` | 8 | 0 |
| Legatus | `master` | 8 | 0 |
| monistudio-v2 | `master` | 7 | 0 |
| TCX-SMART | `main` | 0 | 6 |

Não toquei em nenhum: é trabalho em voo de outro contexto, e commitar às cegas seria
imprudência, não zelo. Uma cópia de diretório preserva tudo isso como está — o risco real
seria um move que falhe no meio, e é por isso que o item 2.2 (parar os containers) importa.
