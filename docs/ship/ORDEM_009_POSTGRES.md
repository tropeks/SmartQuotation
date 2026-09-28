# Ordem 009 — Postgres: produção 15 contra dev e CI 16

> Gate ship do Capitão. Nada nesta ordem foi executado contra o host de produção nem contra
> nenhum banco real — leitura de repositório e patch de CI/docs apenas (contrato de execução
> da ordem: "Fora desta ordem: nada no host de produção").

## 1. Veredito

**O repositório NÃO prova que a produção roda Postgres 15.** A premissa do achado do
Conformador vem de um arquivo (`docker-compose.prod.yml`) que a própria produção **não usa**
— ela roda em container avulso (`sq-prod-db`), não via compose. O indício mais forte que o
repositório contém (o incidente de corrupção de catálogo de 18/07/2026) aponta na direção
contrária: para a produção rodar **16** naquela data. Mas o repo também não prova isso com
certeza, porque não registra se o cluster foi recriado na recuperação do incidente (18/07)
nem com qual imagem. **A prova decisiva não existe no repo — é leitura no host, listada na
§3, para o Capitão executar.**

O resto desta ordem (§4–§5) foi desenhado para não depender do veredito: a suíte passa a
provar as duas majors (15 e 16) e o plano de upgrade é condicional ao resultado da leitura.

---

## 2. Dossiê de evidência

| # | Fonte | Commit/arquivo:linha | O que diz | Peso |
|---|---|---|---|---|
| 1 | `docker-compose.prod.yml` | `4e866b4` (27/06/2026), `docker-compose.prod.yml:37` (`image: postgres:15`) | Declara `postgres:15` para o serviço `db` do compose de produção | **Baixo** — é a origem da premissa "produção = 15", mas o próprio compose **não é o que a produção roda** (item 3) |
| 2 | `scripts/restore_check.sh` | ordem 002 (27/09/2026), `scripts/restore_check.sh:5` e `:63` (`RESTORE_IMAGE="${RESTORE_IMAGE:-postgres:15}"`, comentário "mesma major da produção") | Usa `postgres:15` como imagem efêmera default do drill de restore | **Baixo, circular** — o comentário deriva do item 1 (compose.prod), não de uma leitura independente do host |
| 3 | `docs/HANDOFF_MIGRACAO.md` §2.2 e §4 | texto do doc (sessão de 18/08/2026) | "O SmartQuotation em produção (`sq-web-proto`, `sq-prod-db`, `sq-prod-redis`) usa **volumes nomeados**, não bind mounts" — produção é **container avulso**, não compose | **Alto, mas negativo** — prova que o item 1 não se aplica a produção; não diz qual major |
| 4 | `docker-compose.yml` (dev) | `864e9d4` (05/06/2026), 22 dias **antes** de `docker-compose.prod.yml` existir | Dev sempre foi `postgres:16-alpine`, volume nomeado `sq_postgres_data` (na época, sem o prefixo `sq_dev_`) | **Médio, contextual** — mostra que "dev roda 16" é fato antigo e nunca foi diferente; não fala de produção |
| 5 | Commits `3dacbff`/`e1ee8fc` (18/07/2026), "fix(infra): isola volumes do Compose dev do PGDATA de produção" | mensagem do commit | O `db` do compose de **dev** (`postgres:16-alpine`) montava `sq_postgres_data`, que o Compose prefixa como `smartquotation_sq_postgres_data` — **o mesmo nome do volume real de produção** (`sq-prod-db`). Com `restart: unless-stopped`, isso subiu um **segundo postmaster no mesmo PGDATA de produção** e corrompeu o catálogo (`audit_accesslog`/`accounts_userprofile`) | **Alto** — ver análise abaixo |
| 6 | Mesmo commit, texto da recuperação | mensagem do commit | "recuperadas via restore do dump limpo de 07-16 + migrate" | **Enfraquece o item 5 para o estado ATUAL** — ver ressalva abaixo |

### Por que o item 5 pesa a favor de 16 (não de 15)

O postmaster do Postgres roda `ValidatePgVersion()`/`checkDataDir()` no arranque: ele lê o
arquivo `PG_VERSION` (texto puro, 2–3 bytes) do diretório de dados e **aborta com `FATAL:
database files are incompatible with server`** antes de tocar em qualquer arquivo, se a
major do binário não bater com a do `PG_VERSION` gravado. Isso é comportamento documentado
do Postgres, não uma peculiaridade deste repo.

Consequência: se o PGDATA de produção fosse major **15** e um `postgres:16-alpine` (o `db` de
dev) tentasse montá-lo, o container teria entrado em **crashloop com `FATAL` no log** — sem
escrever nada, sem corromper catálogo, só recusando subir. O que o commit narra é diferente:
**corrupção de catálogo**, o efeito de **dois postmasters da MESMA major escrevendo
concorrentemente no mesmo PGDATA sem coordenação** (WAL de um pisando estado que o outro
assumia consistente) — cenário que só é fisicamente possível se os dois binários (o `db` de
dev, `postgres:16-alpine`, e o `sq-prod-db` de produção) fossem **ambos major 16** em
18/07/2026.

**Ressalva que impede tratar isso como prova para HOJE (item 6):** a recuperação foi "restore
do dump limpo de 07-16 + migrate". Se esse restore **recriou o cluster do zero** — e o repo
não registra com qual imagem —, a major de produção a partir de 18/07/2026 é a da imagem
usada nessa recriação, e nada no repositório diz qual foi. É perfeitamente possível que a
recriação tenha usado `postgres:15` (por exemplo, se quem recuperou seguiu o
`docker-compose.prod.yml`, que já existia desde 27/06 e diz 15) — o que inverteria a
inferência do item 5 para depois de 18/07. **Esta é a maior lacuna do dossiê: não há fonte no
repo sobre a imagem usada nem antes nem depois da recuperação de 18/07.**

### O que o repositório NÃO pode provar

- A major exata do `sq-prod-db` **hoje** (28/09/2026).
- A imagem/tag exata que o `sq-prod-db` usa (não está registrada em nenhum arquivo do repo —
  container avulso, criado fora de qualquer manifesto versionado).
- Se o cluster foi recriado na recuperação de 18/07/2026 e, se sim, com qual major.
- Qualquer coisa sobre o dump de rollback `~/backups/sq/pre_prancha_20260728_143633.sql.gz`
  além do que seu próprio cabeçalho disser quando lido (comando 3 abaixo) — ele não é lido
  aqui, por estar fora do repositório e fora do escopo desta ordem (nenhum acesso ao host).

---

## 3. Comandos de leitura decisivos (para o Capitão — não executados aqui)

Estes três comandos são **leitura pura** (nenhum grava, nenhum reinicia nada) e, juntos,
resolvem a lacuna do dossiê. Rode os três e cruze os resultados — não confie em só um.

```bash
# 1) Tag/imagem declarada do container — mais fraco: uma imagem pode ter sido re-taggeada,
#    ou o rótulo pode não conter a major de forma legível (digest puro).
docker inspect -f '{{.Config.Image}}' sq-prod-db
# Interpretação: string com "15" (ex. "postgres:15", "postgres:15.7") → indício de 15.
# String com "16" → indício de 16. Um digest sha256:... sem tag legível → não decide nada
# sozinho, use o comando 2.

# 2) PG_VERSION no disco — a fonte de verdade: é o arquivo que o PRÓPRIO Postgres grava na
#    inicialização do cluster e que trava a subida (ValidatePgVersion) se não bater com o
#    binário. Não pode "mentir" como uma tag Docker pode.
docker exec sq-prod-db cat /var/lib/postgresql/data/PG_VERSION
# equivalente, se preferir consultar via SQL (mesma fonte, outro caminho):
docker exec sq-prod-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -h 127.0.0.1 -p 5436 -c "SELECT version();"'
# Interpretação: "15" (ou "SELECT version()" citando "PostgreSQL 15.x") → produção é 15 HOJE,
# o plano de upgrade da §5 se aplica tal como escrito. "16" → produção já é 16, pule para a
# "Rota B" da §5 (só alinhar o compose.prod, nenhuma migração de dado).

# 3) Cabeçalho do dump de rollback — segunda fonte independente, sem exec no container (útil
#    para cruzar com o comando 2; datado de 28/07/2026, não necessariamente igual a hoje se
#    algo mudou a major entre 28/07 e 28/09 sem deixar rastro no repo).
zcat ~/backups/sq/pre_prancha_20260728_143633.sql.gz | grep -m1 'Dumped from database version'
# Interpretação: pg_dump/pg_dumpall grava esse comentário com a versão completa do servidor
# de ORIGEM no momento do dump (ex. "-- Dumped from database version 15.7" ou "16.4"). Se
# bater com o comando 2, a major não mudou entre 28/07 e hoje — maior confiança no resultado.
# Se divergir, a major mudou nesse intervalo (rastreie separadamente por quê).
```

Se os comandos 2 e 3 concordarem, trate o resultado como decisivo. Se divergirem, a major
mudou entre 28/07 e hoje e vale investigar quando/por quê antes de agir na §5.

---

## 4. A suíte passa a rodar também na major da produção

Parte em paralelo deste mesmo changeset da ordem 009 (outro agente, mesma ordem — arquivos
citados abaixo fazem parte da entrega da ordem, não desta seção do dossiê):

- **`scripts/restore_check.sh`** deixa de fixar `postgres:15`: sem `RESTORE_IMAGE`, o drill
  passa a usar `postgres:<major lida do cabeçalho "Dumped from database version" do dump
  mais recente>` — a mesma técnica do comando 3 acima, automatizada. Com `RESTORE_IMAGE`
  setado para uma major **menor** que a do dump, o script **reprova** (um drill que restaura
  um dump de major N num Postgres N-1 não é um drill válido). O `restore_last_success` passa
  a gravar `source_major=`/`image=` para tornar isso auditável sem reabrir o dump.
- **`scripts/ci/suite_local_pg.sh <major>`** (novo): roda a suíte Django local
  (`manage.py test apps`, multi-tenant) contra um Postgres efêmero da major pedida, em
  `127.0.0.1`, `--rm` — sem depender da CI. Uso:

  ```bash
  scripts/ci/suite_local_pg.sh 15   # prova local contra a major que a leitura da §3 confirmar
  scripts/ci/suite_local_pg.sh 16   # prova local contra a major que já roda na CI hoje
  ```

- **`docs/patches/009-ci-postgres-matrix.patch`** (novo, para o Capitão aplicar em
  `.github/workflows/ci.yml`, mesmo padrão do `docs/patches/004-ci-import-linter.patch`):
  troca o job único `django-test` (hoje só `postgres:16-alpine`, linha 118 do `ci.yml`) por
  uma **matriz** Postgres 15 e 16, com os jobs nomeados
  `Testes Django (multi-tenant) — Postgres 15` e `Testes Django (multi-tenant) — Postgres 16`.
  **`scripts/ci/suite_receipt.sh`** (a prova headless de suíte via CI, §11 do
  `INFRASTRUCTURE.md`) passa a aceitar tanto o nome de job antigo (`Testes Django
  (multi-tenant)`, para runs anteriores ao patch) quanto os dois nomes da matriz.

**Até o Capitão aplicar o patch**, a prova contra a major real de produção é o comando local
acima (`scripts/ci/suite_local_pg.sh <major>`); depois de aplicado, a CI prova as duas majors
em todo push/PR, e o recibo de suíte (`suite_receipt.sh`) confere ambos os jobs da matriz.

---

## 5. Plano de upgrade 15 → 16

**Condicional ao resultado da §3.** Duas rotas — escolha pela leitura, não pela suposição.

### Rota A — a leitura confirmou 15: upgrade real de dado

#### Pré-requisitos (checklist, nada disto foi instalado nem executado)

- **Backup instalado e um drill verde.** As units das ordens 002/003
  (`ops/systemd/sq-backup.{service,timer}`, `sq-restore-check.{service,timer}`) instaladas no
  host (`docs/INFRASTRUCTURE.md` §6, "Instalar as units"), com `/backups/sq/restore_last_success`
  com menos de 8 dias (o teste de que o backup **restaura**, não só existe — sem isso, o
  upgrade não tem uma rede de segurança provada).
- **`FIELD_ENCRYPTION_KEY` em custódia.** Confirmar `offsite_key_push.sh` já rodou pelo menos
  uma vez (`/var/lib/smartquotation/key-backup/offsite_key_last_success` existe) OU a cópia
  manual do `.env.prod` (custódia do Capitão, `docs/INFRASTRUCTURE.md` §6) está atualizada.
  Sem a chave certa, o dump novo restaura com preços ilegíveis.
- **Imagem de rollback pronta.** A imagem `smartquotation:rollback-20260718` (ou uma mais
  recente equivalente) e o dump verificado mais novo (`restore_last_success`) — não o de
  28/07, que é só o ponto de referência histórico do HANDOFF.
- **Janela de manutenção agendada.** O corte (passos 3–7) exige app parada — não é uma
  migração "sem downtime" (justificativa na próxima subseção).
- **Snapshot da configuração atual do `sq-prod-db`**, para replicar no container novo — ler,
  não assumir:

  ```bash
  # Congela a config ATUAL antes de tocar em qualquer coisa: imagem, env (sem imprimir
  # POSTGRES_PASSWORD em log persistente), rede, mounts, nome.
  docker inspect sq-prod-db > /root/sq-prod-db.inspect.$(date +%Y%m%d%H%M%S).json
  docker exec sq-prod-db env | grep -E '^POSTGRES_(DB|USER)='   # NÃO grave PASSWORD em log
  docker inspect -f '{{json .NetworkSettings.Networks}}' sq-prod-db   # rede(s) que ligam ao sq-web-proto
  ```

  O repo já documenta, de fontes independentes desta ordem, dois pontos da configuração atual
  (preserve os dois no container novo):
  - **Porta 5436 dentro do container** (não é a `POSTGRES_PORT=5432` do Django via rede —
    `scripts/backup_db.sh:27-29`, `docs/INFRASTRUCTURE.md:537-538`).
  - **`-c unix_socket_directories=`** (sem socket Unix, só TCP) — o comentário do
    `docker-compose.yml:9-12` (dev) registra explicitamente: "Mesmo contorno já usado pelo
    Postgres de produção."

  `POSTGRES_DB`/`POSTGRES_USER` e o nome da rede **não estão confirmados no repo** — os valores
  usuais em todo o resto do projeto são `smartquotation`/`sq` (convenção do `.env.prod.example`
  e dos defaults de dev), mas **leia do `docker inspect` real antes de assumir**; não foram
  inventados aqui.

#### Método: `pg_dumpall` (cliente 16) contra o servidor 15 — não `pg_upgrade`/`--link`

- **`pg_upgrade` (inclusive `--link`) exige os binários das DUAS majors acessando a MESMA
  árvore de dados** durante o processo — estruturalmente a mesma categoria de risco do
  incidente de 18/07/2026 (dois postmasters de majors diferentes tocando o mesmo PGDATA), que
  este repositório acabou de gastar um commit inteiro (`3dacbff`/`e1ee8fc`) corrigindo e
  documentando como perigo concreto, não hipotético. Num container avulso, sem orquestração
  (a produção não roda `pg_upgrade` nenhuma vez antes), instalar as duas majors lado a lado e
  rodar o upgrade "no lugar" tem mais partes móveis e mais formas de repetir o mesmo erro.
- **`--link`** (hard link dos arquivos de dado entre cluster antigo e novo) entrelaça os dois
  clusters no nível do sistema de arquivos: um erro no meio do processo pode comprometer
  **ambos**, destruindo justamente o caminho de rollback que este plano exige preservar
  intacto (ver "Volta"). Também exige que velho e novo estejam no **mesmo volume/mount** — o
  oposto do requisito de "volume novo, nunca reaproveitar o nome do antigo" desta seção.
- **Banco pequeno, um tenant.** O MVP tem um único design partner (ENGEMATEX) com um schema —
  não há volume de dados que justifique o ganho de velocidade do `--link` em troca do risco
  acima. `pg_dumpall`/`psql` é mais lento em relógio de parede, mas é o **mesmo mecanismo já
  construído, testado e documentado neste repo** (`backup_db.sh`, `restore_check.sh`) —
  reaproveitar ferramenta provada em vez de introduzir um procedimento novo e nunca
  ensaiado no dia do corte.
- A prática padrão do próprio Postgres para dump/restore entre majors é usar o `pg_dump`/
  `pg_dumpall` da versão **mais nova** (aqui, 16) para ler o servidor **mais velho** (15): o
  cliente novo entende o protocolo do servidor antigo e já produz um dump no formato que o
  servidor novo espera — por isso "cliente 16 contra servidor 15", não o inverso.

#### Passo a passo (bash comentado — nada disto foi executado)

Duas fases: um **ensaio** com a app no ar (mede o tempo e prova que o dump restaura num 16) e
o **corte**, com a app parada, que restaura um dump **completo** tirado com a escrita já
congelada num cluster 16 **vazio**. Não existe "reaplicar o incremental": um segundo
`pg_dumpall` completo aplicado sobre um cluster já populado colide em cada `CREATE` e duplica
ou recusa cada `COPY`. Por isso o container 16 só nasce no corte.

```bash
# como root no host de produção, a partir de /opt/smartquotation
umask 077
WORK=/root/sq-upgrade16          # fora do BACKUP_DIR (/backups/sq): o restore_check.sh
install -d -m 0700 "$WORK" "$WORK/drill"   # recusa RESTORE_DUMP_FILE dentro do BACKUP_DIR

# Senha do 15 lida do env do próprio container, sem ir para argv nem para log: o docker run
# abaixo recebe só o NOME da variável (-e PGPASSWORD).
PGPASSWORD="$(docker exec sq-prod-db printenv POSTGRES_PASSWORD)"; export PGPASSWORD
PGUSER_ATUAL="$(docker exec sq-prod-db printenv POSTGRES_USER)"
PGDB_ATUAL="$(docker exec sq-prod-db printenv POSTGRES_DB)"

# ── 0. Imagem: família debian, não alpine ───────────────────────────────────────
# O sq-prod-db é da família debian se a leitura da §3 mostrar `postgres:15` sem -alpine
# (confira). Trocar de família JUNTO com a major trocaria libc/collation no mesmo corte.
docker pull postgres:16

# ── 1. ENSAIO (app no ar): dump do 15 com o CLIENTE 16 ──────────────────────────
# --network container:sq-prod-db: o cliente divide a rede do sq-prod-db e fala com
# 127.0.0.1:5436, o MESMO caminho do backup_db.sh (não depende de listen_addresses).
ENSAIO="$WORK/sq_ensaio16_$(date +%Y%m%d%H%M%S).sql.gz"
time docker run --rm --network container:sq-prod-db -e PGPASSWORD postgres:16 \
  pg_dumpall -h 127.0.0.1 -p 5436 -U "$PGUSER_ATUAL" | gzip > "$ENSAIO"
gzip -t "$ENSAIO"                                          # integridade
zcat "$ENSAIO" | grep -c -- '-- PostgreSQL database cluster dump complete'   # == 1: não truncou
# (lição já paga: pg_dumpall na porta errada gera 20 bytes com exit 0, INFRASTRUCTURE §6)

# ── 2. ENSAIO: o drill restaura o dump num 16 efêmero, sem rede ─────────────────
# Sem RESTORE_IMAGE: o restore_check.sh lê "Dumped from database version" (15) e sobe
# postgres:15 — o que queremos provar aqui é o 16, então fixe a imagem (major 16 >= 15, aceita).
time BACKUP_DIR="$WORK/drill" RESTORE_DUMP_FILE="$ENSAIO" RESTORE_CHECK_MEDIA=0 \
  RESTORE_IMAGE=postgres:16 RESTORE_DB="$PGDB_ATUAL" ./scripts/restore_check.sh
# Verde = o dump do 15 restaura limpo num 16. Os dois `time` somados são a estimativa do
# tempo de parada (ver "Tempo de parada"). Vermelho: PARE, nada foi tocado.

# ── 3. CORTE (janela de manutenção — app indisponível daqui até o passo 7) ──────
docker stop sq-web-proto                      # congela a escrita
FINAL="$WORK/sq_corte16_$(date +%Y%m%d%H%M%S).sql.gz"
docker run --rm --network container:sq-prod-db -e PGPASSWORD postgres:16 \
  pg_dumpall -h 127.0.0.1 -p 5436 -U "$PGUSER_ATUAL" | gzip > "$FINAL"
gzip -t "$FINAL"
zcat "$FINAL" | grep -c -- '-- PostgreSQL database cluster dump complete'     # == 1
N15="$(docker exec sq-prod-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -XAt -U "$POSTGRES_USER" -h 127.0.0.1 -p 5436 -d "$POSTGRES_DB" -c "SELECT count(*) FROM engematex.quotations_quotation"')"
docker stop sq-prod-db                        # o volume antigo NÃO é tocado nem removido
docker rename sq-prod-db sq-prod-db-pg15-rollback

# ── 4. Postgres 16 NOVO, volume NOVO de nome inequívoco ─────────────────────────
# NUNCA sq_postgres_data / smartquotation_sq_postgres_data (volume REAL do 15, fica de
# rollback) / sq_dev_postgres_data (dev). Incidente de 18/07/2026: confusão de nome de volume.
docker volume create sq_prod_postgres16_data
# Mesmo usuário, senha e banco do 15: o .env.prod da app não muda. Mesma porta (5436), mesmo
# contorno de socket. Rede, restart policy e demais flags: copie do inspect salvo nos
# pré-requisitos (/root/sq-prod-db.inspect.*.json) — não invente.
docker run -d --name sq-prod-db --restart unless-stopped \
  -e POSTGRES_USER="$PGUSER_ATUAL" -e POSTGRES_PASSWORD="$PGPASSWORD" -e POSTGRES_DB="$PGDB_ATUAL" \
  -v sq_prod_postgres16_data:/var/lib/postgresql/data \
  --network "<rede lida do inspect — a que liga ao sq-web-proto>" \
  postgres:16 -c port=5436 -c unix_socket_directories=
until docker exec sq-prod-db pg_isready -h 127.0.0.1 -p 5436 -q; do sleep 1; done

# ── 5. Restore do dump FINAL no 16 vazio ────────────────────────────────────────
# ON_ERROR_STOP=0 como no restore_check.sh: o único ERROR tolerado é 'role "..." already
# exists' (o superusuário que o initdb já criou). Qualquer outro: PARE e vá para "Volta".
zcat "$FINAL" | docker exec -i sq-prod-db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -U "$POSTGRES_USER" -h 127.0.0.1 -p 5436 -d postgres -v ON_ERROR_STOP=0' \
  2> "$WORK/psql_corte16.err"
grep 'ERROR:' "$WORK/psql_corte16.err" | grep -v -E 'role "[^"]+" already exists'   # vazio = ok

# ── 6. Conferência ANTES de religar a app ───────────────────────────────────────
docker exec sq-prod-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -XAt -U "$POSTGRES_USER" -h 127.0.0.1 -p 5436 -d "$POSTGRES_DB" -c "SELECT version()"'   # PostgreSQL 16.x
N16="$(docker exec sq-prod-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -XAt -U "$POSTGRES_USER" -h 127.0.0.1 -p 5436 -d "$POSTGRES_DB" -c "SELECT count(*) FROM engematex.quotations_quotation"')"
[ "$N15" = "$N16" ] || echo "CONTAGEM DIVERGE ($N15 != $N16): PARE, vá para Volta"
# Com a escrita congelada no passo 3, as contagens têm que ser IGUAIS, não "parecidas".

# ── 7. Religa a app ─────────────────────────────────────────────────────────────
docker start sq-web-proto
curl -fsS https://quotation.qtec.me/health/
unset PGPASSWORD

# ── 8. Verificação pós-corte ────────────────────────────────────────────────────
./scripts/backup_db.sh           # primeiro dump nativo do 16 (DB_CONTAINER=sq-prod-db, 5436)
./scripts/restore_check.sh       # sem RESTORE_IMAGE: lê "16" do dump e sobe postgres:16
./scripts/backup_key.sh          # prova de decifra contra o banco novo
# (como root, com o backup.env das units: set -a && . /etc/smartquotation/backup.env && set +a)
# O drill roda sem rede: postgres:16 já tem que estar local (passo 0).
```

#### Verificação pós — resumo

- `SELECT version()` no `sq-prod-db` novo cita `PostgreSQL 16.x` (passo 6).
- Contagem de `engematex.quotations_quotation` **igual** no 15 congelado e no 16 (passo 6).
- `curl -fsS https://quotation.qtec.me/health/` — `200` (passo 7).
- `backup_db.sh` + `restore_check.sh` verdes; o `restore_last_success` grava
  `source_major=16` e `image=postgres:16` (passo 8).
- `backup_key.sh` — prova de decifra `ok` (não `falha`/`sem amostra`).

#### Tempo de parada estimado — faixa honesta, NÃO medida

Não há nenhum número medido neste repositório para o tamanho real do dump de produção nem
para a duração de um `pg_dumpall`/restore contra ele — os testes de backup usam bancos
sintéticos pequenos. **Não invente uma faixa de minutos aqui.** A parada vai do passo 3
(`docker stop sq-web-proto`) ao passo 7 (`/health/` verde): dump final + restore no 16 vazio +
conferência + troca de containers. Os dois termos de dado são medidos pelo **ensaio** (passos
1–2, com a app no ar):

- **Parada ≈ `time` do passo 1 (dump) + `time` do passo 2 (restore no 16 efêmero) + uma folga
  de poucos minutos** para `stop`/`rename`/`run`/`pg_isready`/`start`/`/health/`, que não
  tocam dado.
- Depois de instaladas as units, o **`duration_s` do `restore_last_success`** (drill semanal,
  `docs/INFRASTRUCTURE.md` §6) mede o mesmo termo de restore toda semana — ainda não foi lido
  nem uma vez (units não instaladas, gate ship do Capitão).
- Sem esse ensaio, a única afirmação honesta é: **"desconhecido, provavelmente baixo — banco
  de um único tenant pequeno, mesma ordem de grandeza dos dumps sintéticos de teste (segundos
  a poucos minutos) — mas não agende a janela de manutenção sem medir primeiro."**

#### Volta (rollback)

- O container antigo (`sq-prod-db-pg15-rollback`, sobre o volume original **intocado**)
  fica parado, não removido. Voltar:

  ```bash
  docker stop sq-web-proto
  docker stop sq-prod-db                              # o 16
  docker rename sq-prod-db sq-prod-db-pg16-descartado # não remova: pode ter escrita nova
  docker rename sq-prod-db-pg15-rollback sq-prod-db
  docker start sq-prod-db
  docker start sq-web-proto
  curl -fsS https://quotation.qtec.me/health/
  ```

- **Antes do passo 7**, voltar não perde nada: a app ainda não escreveu no 16.
- **Janela sem perda de dado depois do passo 7:** só enquanto **nada** foi escrito no 16 —
  do `docker start sq-web-proto` até a primeira escrita. Depois desse ponto, qualquer escrita nova (cotação criada/editada) só
  existe no cluster 16; reverter para o 15 perde essas escritas, a não ser que sejam
  reaplicadas manualmente.
- **Depois que o 16 já recebeu escrita:** reverter passa a exigir um dump do 16 e restaurá-lo
  no 15 (downgrade lógico) — que **pode falhar** em `GRANT`/atributos de role específicos de
  16 que o `psql`/servidor 15 não reconhece (o `pg_dumpall` não garante compatibilidade
  retroativa de major). Não trate essa rota como garantida; se chegar a esse ponto, teste o
  dump 16→15 num ambiente isolado antes de aplicar contra o `sq-prod-db-pg15-rollback` real.

### Rota B — a leitura confirmou 16: não há upgrade de dado, só alinhar o repo

Se os comandos da §3 confirmarem que o `sq-prod-db` já é major 16, **não existe migração de
dado a fazer**. O trabalho vira só destravar a divergência documental identificada nesta
ordem:

1. `docker-compose.prod.yml`: trocar `image: postgres:15` (linha 34) por `image: postgres:16`
   — mesma família (debian, sem `-alpine`), coerente com o que a leitura confirmou. **Não é
   uma migração de produção**: esse arquivo não é o que a produção roda (§0/§2 do
   `INFRASTRUCTURE.md`), então a mudança não reinicia nada real — só faz o compose parar de
   mentir sobre a major, caso algum dia alguém decida migrar produção a rodar via compose de
   fato.
2. `scripts/restore_check.sh` já deixa de depender de um número fixo com o patch da §4 (deriva
   a major do cabeçalho do dump) — nada a fazer ali além do que a §4 já entrega.
3. Registrar no `INFRASTRUCTURE.md` (feito nesta mesma ordem, §0) que a major real é 16,
   removendo a suposição de 15 como fato.
4. Nenhuma janela de manutenção, nenhum backup extra, nenhum volume novo — não há corte.

---

## 6. Onde ver a prova

- Este dossiê (§2) é auditável por `git show <commit>` nos commits citados; todos foram
  conferidos diretamente nesta sessão, não citados de memória.
- `docs/patches/009-ci-postgres-matrix.patch`, `scripts/ci/suite_local_pg.sh`,
  `scripts/restore_check.sh` (versão com major derivada do dump) e `scripts/ci/suite_receipt.sh`
  (aceitando o nome de job antigo e os dois da matriz) são entregues por outro agente no
  mesmo changeset desta ordem — não foram escritos nem alterados por este documento.
- `docs/INFRASTRUCTURE.md` recebeu as emendas correspondentes no mesmo changeset (§0, §2, §5,
  §6, §11).

**Nada nesta ordem foi executado contra o host de produção.** A Rota A do plano de upgrade só
deve ser executada depois que o Capitão confirmar 15 pela §3, os pré-requisitos estiverem
marcados e a janela de manutenção estiver agendada.
