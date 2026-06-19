from rest_framework import serializers
from apps.quotations.models import Quotation, QuotationItem

class QuotationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationItem
        fields = ["codigo_item", "descricao", "custo_material", "custo_mo", "custo_total", "sort_order"]
        read_only_fields = fields

class QuotationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.company_name", read_only=True)
    itens = QuotationItemSerializer(many=True, read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "number", "revision", "title", "scope", "status",
            "custo_material", "custo_mo", "custo_total",
            "preco_sem_impostos", "preco_com_impostos",
            "customer_name", "itens"
        ]
        read_only_fields = fields
