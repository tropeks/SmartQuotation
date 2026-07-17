# requirements/

Dois níveis: os `.txt` são a **fonte** (escritos à mão, legíveis, com ranges quando
faz sentido); os `.lock` são o **artefato** (gerados, toda a árvore transitiva travada
em versão exata + hash sha256).

| Arquivo | Papel | Quem consome |
|---|---|---|
| `base.txt` | fonte — deps da app | você edita |
| `base.lock` | lock com hashes | `backend/Dockerfile` (imagem de produção) |
| `ci.txt` | fonte — subconjunto sem docxtpl; inclui weasyprint (o CI instala as libs de pango) | você edita |
| `ci.lock` | lock com hashes | `.github/workflows/ci.yml` |
| `ops.txt` | fonte — deps dos jobs de ops/infra (pyyaml, pip-audit); sem Django | você edita |
| `ops.lock` | lock com hashes | jobs `ops-tests` e `pip-audit` do CI |
| `development.txt` | `-r base.txt` + pytest/ruff — **sem lock**, ver abaixo | venv local |

## Por que lock com hash

`docker build` sem lock resolve as deps no momento do build. Um release upstream
comprometido de qualquer dependência — direta ou transitiva — entraria direto na
imagem de produção sem review, sem diff, e sem forma de reconstruir o que uma imagem
anterior continha durante resposta a incidente. `--require-hashes` recusa qualquer
pacote cujo sha256 não case com o lock.

## Versão velha é tão perigosa quanto versão flutuante

O lock garante que você instala *exatamente* o que revisou. Ele **não** garante que o
que você revisou é seguro. Em 2026-07-17 este repo pinou `Django==5.2.8` achando que
fechava um CVE; o 5.2.8 já tinha 8 meses e **26 advisories** — incluindo outro SQLi de
`FilteredRelation` (a mesma classe de bug do CVE original), corrigido no 5.2.9. O
`--require-hashes` garantiu, com perfeição, a reprodutibilidade da versão furada.

Por isso o CI tem o job **`pip-audit`**, que roda contra `base.lock` e `ci.lock` com a
base de advisories ao vivo e falha em advisory novo. O `assert django >= (5,2,16)` em
`tests/test_requirements_lock.py` é só uma rede offline: piso estático não detecta pin
velho. Se o `pip-audit` falhar, o conserto é subir a versão no `.txt` e regenerar o lock
— não subir o piso do teste.

## Regenerar (obrigatório após editar qualquer `.txt`)

Use `python:3.12-slim` para casar com o runner e com a imagem de produção — regenerar sob
outra minor pode resolver versões diferentes:

```bash
cd backend
docker run --rm -v "$PWD/requirements:/w" -w /w python:3.12-slim bash -c "
  pip install -q pip-tools
  for f in base ci ops; do
    pip-compile --generate-hashes --strip-extras --output-file=\$f.lock \$f.txt
  done"
```

`ops.lock` avisa que `pip` ficou sem pin (o `pip-audit` depende dele). É benigno: o pip já
vem na imagem, então o requisito está satisfeito e o `--require-hashes` instala normal.

Commite o `.txt` e o `.lock` juntos. `tests/test_requirements_lock.py` falha o CI se
um `.lock` sumir, perder os hashes, ou divergir das versões pinadas no `.txt`.

## Atualizar dependências

Para pegar versões novas dentro dos ranges já declarados, regenere os locks
(`pip-compile` sem `--upgrade` respeita o lock existente; use `--upgrade` para subir):

```bash
pip-compile --upgrade --generate-hashes --strip-extras --output-file=requirements/base.lock requirements/base.txt
```

Rode a suíte depois — o lock sobe transitivas também.
