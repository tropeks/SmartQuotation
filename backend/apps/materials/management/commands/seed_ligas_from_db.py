"""
Importa a base ASME II-D 2025 (pricing_engine.asme.ASME_DB) como ligas de CATÁLOGO INATIVAS.

Só chapas (product_form contém "Plate") com extração OK. Agrupa por spec_no + (grade|uns_no);
quando há 2+ linhas para o mesmo material, escolhe a CONSERVADORA (menor S em 40°C; desempate
pela menor curva no total). NÃO ativa nada — as ligas do dropdown continuam vindas de seed_ligas.
Idempotente (update_or_create por código). NÃO toca pricing_engine.asme nem os specs ativos.

Uso: python manage.py tenant_command seed_ligas_from_db --schema=engematex
"""
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.materials.models import LigaMetalurgica
from pricing_engine.asme import ASME_DB


def _sanitize(s):
    return re.sub(r"[^A-Za-z0-9_-]", "_", s)


def _conservadora_key(rec):
    """Ordena para a linha CONSERVADORA: menor S em 40°C primeiro; empate → menor curva total."""
    s = rec.get("allowable_stress_MPa", {}) or {}
    s40 = float(s.get("40", float("inf")))
    total = sum(float(v) for v in s.values())
    return (s40, total)


class Command(BaseCommand):
    help = "Importa chapas da base ASME II-D 2025 como ligas INATIVAS de catálogo (conservadoras)."

    def handle(self, *args, **opts):
        grupos = defaultdict(list)
        for r in ASME_DB:
            if "Plate" not in (r.get("product_form") or ""):
                continue
            if r.get("audit_info", {}).get("extraction_status") != "OK":
                continue
            spec_no = (r.get("spec_no") or "").replace("–", "-")
            ident = r.get("grade") or r.get("uns_no") or ""
            grupos[(spec_no, ident)].append(r)

        criadas = atualizadas = 0
        for (spec_no, ident), recs in grupos.items():
            rec = min(recs, key=_conservadora_key)            # linha conservadora
            codigo = _sanitize(f"{spec_no}-{ident}")
            nome = f"{spec_no} {ident}".strip()
            s_curva = {str(k): float(v) for k, v in (rec.get("allowable_stress_MPa") or {}).items()}
            defaults = dict(
                nome=nome,
                familia=rec.get("nominal_composition") or "",
                spec=nome,
                s_curva=s_curva,
                liga_fator=1,
                densidade_kg_mm3=0,
                preco_fator=1,
                temp_limite_c=370,
                norma="ASME BPVC II-D (M)",
                edicao="2025",
                tabela=(rec.get("table") or "").replace("Table ", ""),
                linha=str(rec.get("line_no", "")),
                is_active=False,
                ordem=999,
            )
            _, created = LigaMetalurgica.objects.update_or_create(codigo=codigo, defaults=defaults)
            criadas += int(created)
            atualizadas += int(not created)

        self.stdout.write(self.style.SUCCESS(
            f"Ligas ASME II-D (chapas, inativas): {criadas} criadas, {atualizadas} atualizadas."))
