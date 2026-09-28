# Ordem 007 — revisão MANTÉM o número e sobe `revision` (decisão do Capitão
# 01M3JEK53Y43C5A55X0ANSA4B5). `number` deixa de ser UNIQUE sozinho: a identidade de uma
# cotação passa a ser o PAR (number, revision) — a UniqueConstraint abaixo é o que garante
# isso no banco (o alocador `services.allocate_revision` garante em cima, com
# select_for_update; a constraint é o backstop contra corrida).
#
# IRREVERSÍVEL na prática assim que a primeira revisão repetir um `number`: reverter esta
# migração recriaria a UNIQUE antiga em `number` sozinho, que qualquer par de linhas com o
# mesmo `number` (duas revisões da mesma cotação) violaria. O RunPython reverso RECUSA
# desfazer nesse caso, com uma mensagem clara (em vez do Postgres estourar um erro de
# constraint cru no meio da migração) — ver `_refuse_downgrade_if_duplicate_numbers`.
from django.db import migrations, models


def _noop_forward(apps, schema_editor):
    """Forward não precisa fazer nada: a mudança é só de SCHEMA (AlterField + constraint),
    sem dado para migrar — `number` já está preenchido em toda linha existente."""


def _refuse_downgrade_if_duplicate_numbers(apps, schema_editor):
    """Guarda do reverse: recusa desfazer a migração se já existe `number` repetido (ou
    seja, se a feature já foi usada — uma revisão real que manteve o número). Reverter sem
    esta guarda deixaria o Django tentar recriar `UniqueConstraint(number)` e o Postgres
    estourar `duplicate key value violates unique constraint` — um erro de banco cru, sem
    contexto, no meio de uma migração que pode incluir outras operações depois dela."""
    Quotation = apps.get_model("quotations", "Quotation")
    duplicados = (
        Quotation.objects.values("number")
        .annotate(n=models.Count("id"))
        .filter(n__gt=1)
        .order_by("number")
    )
    if duplicados.exists():
        exemplos = ", ".join(d["number"] for d in duplicados[:10])
        total = duplicados.count()
        raise RuntimeError(
            "Não é possível reverter a migração 0010 (quotations): existem "
            f"{total} número(s) de cotação repetido(s) entre revisões (ex.: {exemplos}). "
            "Reverter recriaria a UniqueConstraint antiga em 'number' sozinho, que essas "
            "linhas violam. Isto significa que a feature de revisão-mantém-número já foi "
            "usada em produção — reverter o CÓDIGO é seguro, mas reverter esta MIGRAÇÃO "
            "não é: consolide/renumere as cotações duplicadas primeiro, ou aceite que o "
            "schema fica como está."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('quotations', '0009_itemoperation_taxa_hora_hm_sugerida_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quotation',
            name='number',
            field=models.CharField(db_index=True, max_length=50),
        ),
        migrations.AddConstraint(
            model_name='quotation',
            constraint=models.UniqueConstraint(
                fields=('number', 'revision'), name='uniq_quotation_number_revision'
            ),
        ),
        migrations.RunPython(_noop_forward, reverse_code=_refuse_downgrade_if_duplicate_numbers),
    ]
