"""Extrai o gabarito completo do Permutador BEU da planilha ENGEMATEX → seeds/beu_ground_truth.json.

Aba 'PERMUTADOR "BEM" - ORÇAMENTO' (o título interno diz BEM, mas é o arquivo BEU).
Colunas-chave: 7=label · 72=peso_liq · 78=peso_bruto · 84=PREÇO R$.
Cada "bloco" ocupa 2 linhas (header + dados). Material: preço = peso_bruto × price_kgf.
"""
import glob, json, os

import openpyxl

SRC = glob.glob("/home/rcosta00/dev/uploads/*BEU*.xlsx")[0]
OUT = os.path.join(os.path.dirname(__file__), "..", "pricing_engine", "seeds", "beu_ground_truth.json")

# fronteiras de seção por linha (inclusive), derivadas do mapa da planilha
SECOES = [
    ("feixe_material", 194, 280),
    ("casco_material", 282, 356),
    ("cabecote_material", 358, 436),
    ("feixe_ops", 438, 556),     # espelho, chicanas, prep, tubos-U, trat. térmico
    ("casco_ops", 558, 904),
    ("cabecote_ops", 906, 1096),
    ("finalizacao", 1098, 1173),  # inspeção, teste hidro, docs, ferramentas
]


def secao(row):
    for nome, a, b in SECOES:
        if a <= row <= b:
            return nome
    return "outro"


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
    ws = wb['PERMUTADOR "BEM" - ORÇAMENTO']
    rows = list(ws.iter_rows(min_row=1, max_row=1198, max_col=90, values_only=True))

    def cell(r, c):
        return rows[r - 1][c - 1]

    blocos = []
    for i in range(1, len(rows) + 1):
        preco = cell(i, 84)
        if not isinstance(preco, (int, float)) or preco == 0:
            continue
        # label: col7/col2 desta linha ou das 2 acima
        lbl = None
        for rr in (i, i - 1, i - 2):
            if rr < 1:
                continue
            for c in (7, 2):
                v = cell(rr, c)
                if isinstance(v, str) and v.strip() and v.strip() not in ("x", "SIM", "NÃO", "APLICÁVEL"):
                    lbl = v.strip().replace("\n", " ")
                    break
            if lbl:
                break
        peso_liq = cell(i, 72)
        peso_br = cell(i, 78)
        material = cell(i, 54) or cell(i - 2, 54)
        b = {"row": i, "secao": secao(i), "label": lbl, "preco": round(float(preco), 2)}
        if isinstance(peso_br, (int, float)) and peso_br:
            b["peso_bruto"] = round(float(peso_br), 3)
            b["peso_liq"] = round(float(peso_liq), 3) if isinstance(peso_liq, (int, float)) else None
            b["material"] = material if isinstance(material, str) else None
            b["price_kgf"] = round(float(preco) / float(peso_br), 3)
            b["tipo"] = "material"
        else:
            b["tipo"] = "operacao"
        blocos.append(b)

    total = round(sum(b["preco"] for b in blocos), 2)
    por_secao = {}
    for b in blocos:
        por_secao[b["secao"]] = round(por_secao.get(b["secao"], 0) + b["preco"], 2)

    doc = {
        "fonte": os.path.basename(SRC),
        "aba": 'PERMUTADOR "BEM" - ORÇAMENTO',
        "designacao_tema": "BEU",
        "descricao": "Permutador de calor casco-tubo BEU (bonnet + casco 1 passe + feixe em U) — Petrobras RPBC",
        "custo_total_com_impostos": 128160.0,
        "preco_venda_com_impostos": 160200.0,
        "preco_venda_sem_impostos": 146103.0,
        "fator_comercial": 1.25,
        "icms_pct": 9.0,
        "ipi_pct": 0.0,
        "ncm": "8419 5090",
        "peso_liquido_total_kgf": 3016.0,
        "soma_blocos": total,
        "n_blocos": len(blocos),
        "por_secao": por_secao,
        "blocos": blocos,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"Gravado {OUT}")
    print(f"  blocos={len(blocos)}  soma=R$ {total:,.2f}  (gabarito=R$ 128.160)")
    for s, v in por_secao.items():
        print(f"    {s:20} R$ {v:>12,.2f}")


if __name__ == "__main__":
    main()
