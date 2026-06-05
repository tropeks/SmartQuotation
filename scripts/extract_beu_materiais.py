"""Extrai a tabela de materiais do BEU com dimensões → pricing_engine/seeds/beu_materiais.json.

Lê cada bloco de material (header com rótulos de dimensão + linha de dados) e captura
todas as dimensões nomeadas, material, peso_liq, peso_bruto, price_kgf e uma 'familia'
geométrica inferida do conjunto de dimensões (para casar com a fórmula de peso).
"""
import glob, json, os
import openpyxl

SRC = glob.glob("/home/rcosta00/dev/uploads/*BEU*.xlsx")[0]
OUT = os.path.join(os.path.dirname(__file__), "..", "pricing_engine", "seeds", "beu_materiais.json")

SECOES = [("feixe_material", 194, 280), ("casco_material", 282, 356),
          ("cabecote_material", 358, 436)]


def secao(r):
    for n, a, b in SECOES:
        if a <= r <= b:
            return n
    return "outro"


def familia(label, dims):
    L = (label or "").upper()
    keys = set(dims)
    if "TUBO" in L:
        return "tubo"
    if "TAMPO" in L:
        return "tampo_2_1"
    if "PESCOÇO" in L or "PESCOCO" in L:
        return "pipe"
    if "FLANGE" in L and "PRINCIPAL" in L:
        return "anel"      # flange principal = anel maciço
    if "FLANGE" in L:
        return "flange_wn"  # flange comercial (preço por tabela)
    if "ANEL" in L:
        return "anel"
    if "VIROLA" in L:
        return "chapa_retangular"
    if "ESPELHO" in L or "DISCO" in L or "CHAPA" in L or "DIVISORA" in L:
        return "disco" if ("OD" in keys or "OD DISCO" in keys) else "chapa_retangular"
    return "outro"


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
    ws = wb['PERMUTADOR "BEM" - ORÇAMENTO']
    rows = list(ws.iter_rows(min_row=1, max_row=1198, max_col=90, values_only=True))

    def cell(r, c):
        return rows[r - 1][c - 1] if 1 <= r <= len(rows) else None

    DIM_LABELS = ["ESP.", "ESP", "LARGURA", "COMPR.", "OD", "ID", "OD DISCO",
                  "ND", "SCH", "RATING", "QUANTIDADE", "DIÂMETRO", "TIPO", "FACE"]
    mats = []
    for i in range(194, 437):
        peso_br = cell(i, 78)
        preco = cell(i, 84)
        if not (isinstance(peso_br, (int, float)) and peso_br):
            continue
        if not (isinstance(preco, (int, float)) and preco):
            continue
        hdr = {}
        for ci, v in enumerate(rows[i - 1], start=1):  # dims na MESMA linha? header é i-1? testar i-2 e i-1
            pass
        # o header de dimensões fica 2 linhas acima (linha do label)
        hdr = {}
        for ci, v in enumerate(rows[i - 3], start=1):
            if isinstance(v, str) and v.strip() and v.strip() not in ("x",):
                hdr[v.strip()] = ci
        dims = {}
        for name, c in hdr.items():
            val = cell(i, c)
            if isinstance(val, (int, float, str)) and name not in ("P.E.", "PESO\nESPECÍF.", "PESO LÍQ.", "PESO BR.", "PREÇO R$"):
                dims[name] = round(val, 3) if isinstance(val, float) else val
        label = None
        for c in (7, 2):
            v = cell(i - 2, c)
            if isinstance(v, str) and v.strip():
                label = v.strip().replace("\n", " "); break
        material = None
        for c in (54,):
            v = cell(i - 2, c) or cell(i, c)
            if isinstance(v, str) and v.strip():
                material = v.strip()
        peso_liq = cell(i, 72)
        fam = familia(label, dims)
        mats.append({
            "row": i, "secao": secao(i), "label": label, "familia": fam,
            "material": material, "dims": dims,
            "peso_liq": round(float(peso_liq), 3) if isinstance(peso_liq, (int, float)) else None,
            "peso_bruto": round(float(peso_br), 3),
            "preco": round(float(preco), 2),
            "price_kgf": round(float(preco) / float(peso_br), 3),
        })

    soma = round(sum(m["preco"] for m in mats), 2)
    fam_count = {}
    for m in mats:
        fam_count[m["familia"]] = fam_count.get(m["familia"], 0) + 1
    doc = {"fonte": os.path.basename(SRC), "n_materiais": len(mats),
           "soma_preco": soma, "familias": fam_count, "materiais": mats}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"Gravado {OUT}")
    print(f"  materiais={len(mats)}  soma=R$ {soma:,.2f}")
    print(f"  famílias: {fam_count}")
    print("  amostra (familia | label | dims | peso_br | price_kgf):")
    for m in mats:
        print(f"    {m['familia']:18} {str(m['label'])[:22]:22} {m['material']} br={m['peso_bruto']:>8} kgf | {m['price_kgf']} R$/kgf | dims={m['dims']}")


if __name__ == "__main__":
    main()
