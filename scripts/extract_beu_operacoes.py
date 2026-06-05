"""Extrai a tabela paramétrica de operações do BEU → pricing_engine/seeds/beu_operacoes.json.

Cada bloco de operação (2 linhas: header + dados) é decomposto lendo os rótulos do header
e casando com os valores na linha de dados. Classifica em:
  - mao_obra  : tem HORAS + R$/HORA  → custo = horas × rate × FC + ajuste  (FC escala)
  - servico   : R$/SV, R$/TRANSP, R$/FERR, R$/TUBO, R$/ANEL, R$/kgf — custo fixo (terceiros/insumo)
Guarda horas, rate, ajuste, quant e o preço do gabarito (para reconciliar).
"""
import glob, json, os
import openpyxl

SRC = glob.glob("/home/rcosta00/dev/uploads/*BEU*.xlsx")[0]
OUT = os.path.join(os.path.dirname(__file__), "..", "pricing_engine", "seeds", "beu_operacoes.json")

SECOES = [("feixe_ops", 438, 556), ("casco_ops", 558, 904),
          ("cabecote_ops", 906, 1096), ("finalizacao", 1098, 1173)]


def secao(r):
    for n, a, b in SECOES:
        if a <= r <= b:
            return n
    return "outro"


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
    ws = wb['PERMUTADOR "BEM" - ORÇAMENTO']
    rows = list(ws.iter_rows(min_row=1, max_row=1198, max_col=90, values_only=True))

    def cell(r, c):
        return rows[r - 1][c - 1] if 1 <= r <= len(rows) else None

    ops = []
    code_seen = {}
    for i in range(438, 1174):
        preco = cell(i, 84)
        if not isinstance(preco, (int, float)) or preco == 0:
            continue
        if isinstance(cell(i, 78), (int, float)) and cell(i, 78):
            continue  # material, tratado à parte
        # header = linha i-2: mapa rótulo->coluna
        hdr = {}
        for ci, v in enumerate(rows[i - 3], start=1):
            if isinstance(v, str) and v.strip() and v.strip() not in ("x",):
                hdr[v.strip()] = ci
        # valor na linha de dados i para um rótulo
        def val(name):
            c = hdr.get(name)
            return cell(i, c) if c else None

        label = None
        for rr, c in ((i, 7), (i, 2), (i - 2, 7), (i - 2, 2)):
            v = cell(rr, c)
            if isinstance(v, str) and v.strip() and v.strip() not in ("x", "SIM", "NÃO", "APLICÁVEL"):
                label = v.strip().replace("\n", " "); break

        horas = val("HORAS")
        rate = val("R$ / HORA")
        ajuste = val("AJUSTE") or 0
        is_labor = isinstance(horas, (int, float)) and isinstance(rate, (int, float))
        sec = secao(i)
        # code estável: SECAO-label-ocorrência
        base = "".join(ch for ch in (label or "OP").upper() if ch.isalnum())[:18]
        code_seen[base] = code_seen.get(base, 0) + 1
        code = f"{sec[:3].upper()}-{base}-{code_seen[base]}"

        op = {
            "code": code, "row": i, "secao": sec, "label": label,
            "tipo": "mao_obra" if is_labor else "servico",
            "preco_gabarito": round(float(preco), 2),
        }
        if is_labor:
            op["horas"] = round(float(horas), 3)
            op["rate"] = round(float(rate), 2)
            op["ajuste"] = round(float(ajuste), 2)
            op["preco_calc"] = round(float(horas) * float(rate) + float(ajuste), 2)
        else:
            op["preco_fixo"] = round(float(preco), 2)
        ops.append(op)

    labor = [o for o in ops if o["tipo"] == "mao_obra"]
    serv = [o for o in ops if o["tipo"] == "servico"]
    soma_labor = round(sum(o["preco_gabarito"] for o in labor), 2)
    soma_serv = round(sum(o["preco_gabarito"] for o in serv), 2)
    # quão bem horas×rate+ajuste reproduz o gabarito (deve ser ~exato p/ mão de obra)
    erro = [(o["code"], o["preco_gabarito"], o["preco_calc"])
            for o in labor if abs(o["preco_calc"] - o["preco_gabarito"]) > 0.5]
    doc = {"fonte": os.path.basename(SRC), "n_ops": len(ops),
           "n_mao_obra": len(labor), "n_servico": len(serv),
           "soma_mao_obra": soma_labor, "soma_servico": soma_serv,
           "operacoes": ops}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"Gravado {OUT}")
    print(f"  ops={len(ops)}  mao_obra={len(labor)} (R$ {soma_labor:,.2f})  servico={len(serv)} (R$ {soma_serv:,.2f})")
    print(f"  divergências horas×rate vs gabarito: {len(erro)}")
    for e in erro[:15]:
        print("   ", e)


if __name__ == "__main__":
    main()
