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
| `development.txt` | `-r base.txt` + pytest/ruff | venv local |

## Por que lock com hash

`docker build` sem lock resolve as deps no momento do build. Um release upstream
comprometido de qualquer dependência — direta ou transitiva — entraria direto na
imagem de produção sem review, sem diff, e sem forma de reconstruir o que uma imagem
anterior continha durante resposta a incidente. `--require-hashes` recusa qualquer
pacote cujo sha256 não case com o lock.

## Regenerar (obrigatório após editar qualquer `.txt`)

```bash
cd backend
pip install pip-tools
pip-compile --generate-hashes --strip-extras --output-file=requirements/base.lock requirements/base.txt
pip-compile --generate-hashes --strip-extras --output-file=requirements/ci.lock requirements/ci.txt
```

Commite o `.txt` e o `.lock` juntos. `tests/test_requirements_lock.py` falha o CI se
um `.lock` sumir, perder os hashes, ou divergir das versões pinadas no `.txt`.

## Atualizar dependências

Para pegar versões novas dentro dos ranges já declarados, regenere os locks
(`pip-compile` sem `--upgrade` respeita o lock existente; use `--upgrade` para subir):

```bash
pip-compile --upgrade --generate-hashes --strip-extras --output-file=requirements/base.lock requirements/base.txt
```

Rode a suíte depois — o lock sobe transitivas também.
