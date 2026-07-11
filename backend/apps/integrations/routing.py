from apps.integrations.nomus.models import NomusIntegrationConfig
from apps.integrations.sap_b1.models import SapB1IntegrationConfig


def get_active_erp():
    if NomusIntegrationConfig.objects.filter(enabled=True).exists():
        return "nomus"
    if SapB1IntegrationConfig.objects.filter(enabled=True).exists():
        return "sap_b1"
    return "none"
