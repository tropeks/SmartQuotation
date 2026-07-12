from datetime import timedelta
from decimal import Decimal
from django.db import IntegrityError, transaction
from django.utils import timezone
from apps.audit.services import log_access
from apps.engineering_params.models import Rate, RateSuggestion
from apps.production.models import ActualRate

N_MINIMO = 20
CONF_MINIMA = Decimal('0.70')
DELTA_MINIMO_PCT = Decimal('5.0')  # só sugere se desvio absoluto >= 5%


def generate_suggestions():
    """Escaneia ActualRate elegível (N>=20, conf>=70%) e cria sugestões pendentes.
    Idempotente: não duplica se já existe pending para a operação.
    Retorna lista de RateSuggestion criadas nesta chamada.
    """
    criadas = []
    for ar in ActualRate.objects.filter(sample_count__gte=N_MINIMO, confidence__gte=CONF_MINIMA):
        rate_vigente = Rate.objects.vigente(ar.operacao)
        if not rate_vigente:
            continue
        if rate_vigente.rate_hh == 0:
            continue
        delta = (ar.mean_rate - rate_vigente.rate_hh) / rate_vigente.rate_hh * 100
        delta = max(Decimal('-9999.99'), min(Decimal('9999.99'), delta))
        if abs(delta) < DELTA_MINIMO_PCT:
            continue
        if RateSuggestion.objects.filter(operacao=ar.operacao, status='pending').exists():
            continue
        try:
            s = RateSuggestion.objects.create(
                operacao=ar.operacao,
                actual_mean_rate=ar.mean_rate,
                current_rate_hh=rate_vigente.rate_hh,
                delta_pct=delta.quantize(Decimal('0.01')),
                n_samples=ar.sample_count,
                confidence=ar.confidence,
            )
            criadas.append(s)
        except IntegrityError:
            # Corrida: outro worker criou a sugestão pending entre o exists() e o create().
            # A constraint garante integridade; silenciamos e seguimos.
            continue
    return criadas


def apply_suggestion(pk, user, request=None):
    """Aceita sugestão: fecha o Rate vigente e cria nova versão com o valor sugerido —
    mesmo caminho de edição versionada da calibração (T2). Se já existe uma versão de
    hoje (2º apply no mesmo dia), atualiza-a em vez de duplicar. Audita com
    origem='apontamento' quando `request` é fornecido."""
    with transaction.atomic():
        s = RateSuggestion.objects.select_for_update().get(pk=pk, status='pending')
        today = timezone.localdate()
        vigente = Rate.objects.vigente(s.operacao)
        current_rate = Rate.objects.select_for_update().get(pk=vigente.pk) if vigente is not None else None

        previous_payload = None
        if current_rate is not None:
            previous_payload = {
                'rate_hh': str(current_rate.rate_hh),
                'rate_hm': str(current_rate.rate_hm) if current_rate.rate_hm is not None else None,
            }

        if current_rate is not None and current_rate.valid_from == today:
            current_rate.rate_hh = s.actual_mean_rate
            current_rate.save(update_fields=['rate_hh'])
            new_rate = current_rate
        else:
            rate_hm = current_rate.rate_hm if current_rate is not None else Decimal('0.00')
            if current_rate is not None:
                current_rate.valid_until = today - timedelta(days=1)
                current_rate.save(update_fields=['valid_until'])
            new_rate = Rate.objects.create(
                operacao=s.operacao,
                rate_hh=s.actual_mean_rate,
                rate_hm=rate_hm,
                valid_from=today,
                valid_until=None,
            )

        s.status = 'accepted'
        s.resolved_at = timezone.now()
        s.resolved_by = user
        s.save()

        if request is not None:
            log_access(request, 'rate_change', new_rate, {
                'operacao': s.operacao,
                'origem': 'apontamento',
                'suggestion_id': s.pk,
                'anterior': previous_payload,
                'novo': {
                    'rate_hh': str(new_rate.rate_hh),
                    'rate_hm': str(new_rate.rate_hm) if new_rate.rate_hm is not None else None,
                },
            })
    return s


def dismiss_suggestion(pk, user):
    """Descarta sugestão sem criar Rate."""
    with transaction.atomic():
        s = RateSuggestion.objects.select_for_update().get(pk=pk, status='pending')
        s.status = 'dismissed'
        s.resolved_at = timezone.now()
        s.resolved_by = user
        s.save()
    return s
