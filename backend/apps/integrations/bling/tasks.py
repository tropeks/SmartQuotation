from celery import shared_task
from django.db.models import Prefetch
from django_tenants.utils import schema_context

from apps.integrations.bling.client import BlingClient, BlingClientError, BlingTransientError
from apps.integrations.bling.models import BlingExportLog, BlingIntegrationConfig
from apps.production.models import OFItem, OrdemFabricacao


def _build_nfe_payload(of: OrdemFabricacao) -> dict:
    customer = of.quotation.customer
    items = []
    for item in of.itens.all():
        items.append({
            "descricao": item.descricao,
            "quantidade": 1,
            "valor": str(item.custo_total),
        })
    return {
        "tipo": "1",
        "numero": of.number,
        "naturezaOperacao": "Venda",
        "contato": {
            "cpfCnpj": customer.cnpj or "",
            "nome": customer.company_name,
        },
        "itens": items,
    }


def export_of_to_bling_for_schema(of_id: int, tenant_schema: str) -> dict:
    with schema_context(tenant_schema):
        of = OrdemFabricacao.objects.select_related(
            "quotation__customer"
        ).prefetch_related(
            Prefetch("itens", queryset=OFItem.objects.order_by("sort_order", "codigo_item", "pk"))
        ).get(pk=of_id)
        config = BlingIntegrationConfig.objects.filter(enabled=True).first()
        if config is None:
            raise BlingClientError("Integracao Bling nao esta habilitada para este tenant.")

        payload = _build_nfe_payload(of)
        client = BlingClient(config=config)
        try:
            response = client.post_nfe(payload)
            bling_nfe_id = str(response.get("id", ""))
            BlingExportLog.objects.create(
                of_id=of_id,
                status=BlingExportLog.STATUS_SUCCESS,
                bling_nfe_id=bling_nfe_id,
            )
            return {"status": "success", "bling_nfe_id": bling_nfe_id}
        except BlingClientError as exc:
            BlingExportLog.objects.create(
                of_id=of_id,
                status=BlingExportLog.STATUS_ERROR,
                error=str(exc),
            )
            raise


@shared_task(
    bind=True,
    name="integrations.bling.export_of_to_bling",
    autoretry_for=(BlingTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def export_of_to_bling(self, of_id: int, tenant_schema: str) -> dict:
    return export_of_to_bling_for_schema(of_id, tenant_schema)
