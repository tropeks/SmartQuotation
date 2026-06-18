from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from apps.quotations.models import Quotation
from apps.quotations.serializers import QuotationSerializer
from apps.tema_templates.services import estimate_complete

class QuotationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Quotation.objects.all()
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticated]

class PermutadorEstimateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        designacao = data.get("designacao")
        if not designacao:
            raise ValidationError({"designacao": "Campo obrigatório."})
            
        fator_correcao_mo = data.get("fator_correcao_mo")

        resultado = estimate_complete(
            designacao=designacao,
            params=data,
            fator_correcao_mo=fator_correcao_mo
        )
        
        if not resultado:
            raise ValidationError({"detail": "Não foi possível estimar. Verifique a designação."})
            
        return Response({
            "custo_material": resultado.get("custo_material"),
            "custo_mao_obra": resultado.get("custo_mao_obra"),
            "custo_servicos": resultado.get("custo_servicos"),
            "custo_total": resultado.get("custo_total", 
                           resultado.get("custo_material", 0) + 
                           resultado.get("custo_mao_obra", 0) + 
                           resultado.get("custo_servicos", 0)),
            "preco_com_impostos": resultado.get("preco_com_impostos")
        })
