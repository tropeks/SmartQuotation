from decimal import Decimal
from django.utils import timezone
from apps.engineering_params.models import Rate, RateSuggestion
from apps.production.models import ActualRate

N_MINIMO = 20
CONF_MINIMA = Decimal('0.70')
DELTA_MINIMO_PCT = Decimal('5.0')  # só sugere se desvio absoluto > 5%


def generate_suggestions():
    """Escaneia ActualRate elegível (N>=20, conf>70%) e cria sugestões pendentes.
    Idempotente: não duplica se já existe pending para a operação.
    Retorna lista de RateSuggestion criadas nesta chamada.
    """
    criadas = []
    for ar in ActualRate.objects.filter(sample_count__gte=N_MINIMO, confidence__gt=CONF_MINIMA):
        rate_vigente = Rate.objects.vigente(ar.operacao)
        if not rate_vigente:
            continue
        if rate_vigente.rate_hh == 0:
            continue
        delta = (Decimal(str(ar.mean_rate)) - rate_vigente.rate_hh) / rate_vigente.rate_hh * 100
        if abs(delta) < DELTA_MINIMO_PCT:
            continue
        if RateSuggestion.objects.filter(operacao=ar.operacao, status='pending').exists():
            continue
        s = RateSuggestion.objects.create(
            operacao=ar.operacao,
            actual_mean_rate=ar.mean_rate,
            current_rate_hh=rate_vigente.rate_hh,
            delta_pct=delta.quantize(Decimal('0.01')),
            n_samples=ar.sample_count,
            confidence=ar.confidence,
        )
        criadas.append(s)
    return criadas


def apply_suggestion(pk, user):
    """Aceita sugestão: cria novo Rate vigente a partir de hoje e marca suggestion como accepted."""
    from django.db import transaction
    with transaction.atomic():
        s = RateSuggestion.objects.select_for_update().get(pk=pk, status='pending')
        Rate.objects.create(
            operacao=s.operacao,
            rate_hh=s.actual_mean_rate,
            rate_hm=None,
            valid_from=timezone.now().date(),
        )
        s.status = 'accepted'
        s.resolved_at = timezone.now()
        s.resolved_by = user
        s.save()
    return s


def dismiss_suggestion(pk, user):
    """Descarta sugestão sem criar Rate."""
    from django.db import transaction
    with transaction.atomic():
        s = RateSuggestion.objects.select_for_update().get(pk=pk, status='pending')
        s.status = 'dismissed'
        s.resolved_at = timezone.now()
        s.resolved_by = user
        s.save()
    return s
