"""
Testes TDD H2.3 — Learning Engine (service + views).

Cobre os 15 cenários do motor de aprendizado de rates:
- LearningEngineServiceTests: generate_suggestions / apply_suggestion / dismiss_suggestion
- LearningEngineSuggestionViewTests: lista + aplicar + descartar (HTTP)

Usa TenantTestCase: as tabelas de TENANT_APPS só existem no schema do tenant de teste.
Self-contained: cria Rate vigente e ActualRate no setUp / por teste.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from apps.engineering_params.models import Rate, RateSuggestion
from apps.engineering_params.services import (
    apply_suggestion,
    dismiss_suggestion,
    generate_suggestions,
)
from apps.production.models import ActualRate

User = get_user_model()


class LearningEngineServiceTests(TenantTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eng_learn", password="x")
        # Rate vigente desde o passado, sem fim → vigente hoje.
        self.rate = Rate.objects.create(
            operacao="TEST_OP",
            rate_hh=Decimal("100.00"),
            rate_hm=Decimal("0.00"),
            valid_from=date(2025, 1, 1),
        )

    # ---- generate_suggestions ----

    def test_sem_amostras_nao_gera(self):
        """N=5 < N_MINIMO(20) → não gera."""
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=5,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.80"),
        )
        self.assertEqual(generate_suggestions(), [])
        self.assertEqual(RateSuggestion.objects.count(), 0)

    def test_baixa_confianca_nao_gera(self):
        """N=25 mas confidence=0.50 < 0.70 → não gera."""
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.50"),
        )
        self.assertEqual(generate_suggestions(), [])
        self.assertEqual(RateSuggestion.objects.count(), 0)

    def test_delta_pequeno_nao_gera(self):
        """delta=4% < 5% mínimo → não gera."""
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("104.00"), confidence=Decimal("0.80"),
        )
        self.assertEqual(generate_suggestions(), [])
        self.assertEqual(RateSuggestion.objects.count(), 0)

    def test_gera_suggestion_elegivel(self):
        """N=25, conf=0.80, delta=15% → 1 suggestion pending."""
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.80"),
        )
        criadas = generate_suggestions()
        self.assertEqual(len(criadas), 1)
        s = criadas[0]
        self.assertEqual(s.operacao, "TEST_OP")
        self.assertEqual(s.status, "pending")
        self.assertEqual(s.delta_pct, Decimal("15.00"))
        self.assertEqual(s.current_rate_hh, Decimal("100.00"))
        self.assertEqual(s.n_samples, 25)
        self.assertEqual(RateSuggestion.objects.filter(status="pending").count(), 1)

    def test_idempotente(self):
        """Segunda chamada com mesmos dados não duplica a sugestão pending."""
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.80"),
        )
        first = generate_suggestions()
        self.assertEqual(len(first), 1)
        second = generate_suggestions()
        self.assertEqual(second, [])
        self.assertEqual(RateSuggestion.objects.count(), 1)

    def test_sem_rate_vigente_pula(self):
        """ActualRate de uma operação sem Rate vigente → pula (não gera)."""
        ActualRate.objects.create(
            operacao="OP_SEM_RATE", sample_count=25,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.80"),
        )
        self.assertEqual(generate_suggestions(), [])
        self.assertEqual(RateSuggestion.objects.count(), 0)

    def test_delta_negativo_gera(self):
        """mean=80 vs 100 → delta=-20% (abs>5) → gera com delta_pct negativo."""
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("80.00"), confidence=Decimal("0.80"),
        )
        criadas = generate_suggestions()
        self.assertEqual(len(criadas), 1)
        self.assertEqual(criadas[0].delta_pct, Decimal("-20.00"))
        self.assertLess(criadas[0].delta_pct, 0)

    # ---- apply_suggestion ----

    def test_apply_cria_rate_novo(self):
        """apply cria Rate novo com rate_hh=actual_mean_rate e valid_from=hoje."""
        s = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )
        antes = Rate.objects.filter(operacao="TEST_OP").count()
        apply_suggestion(s.pk, self.user)
        self.assertEqual(Rate.objects.filter(operacao="TEST_OP").count(), antes + 1)
        novo = Rate.objects.vigente("TEST_OP")
        self.assertEqual(novo.rate_hh, Decimal("115.00"))
        self.assertEqual(novo.valid_from, timezone.now().date())

    def test_apply_marca_accepted(self):
        s = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )
        apply_suggestion(s.pk, self.user)
        s.refresh_from_db()
        self.assertEqual(s.status, "accepted")
        self.assertEqual(s.resolved_by, self.user)
        self.assertIsNotNone(s.resolved_at)

    def test_apply_nao_pending_levanta(self):
        """apply numa sugestão já accepted → levanta DoesNotExist."""
        s = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"), status="accepted",
        )
        with self.assertRaises(ObjectDoesNotExist):
            apply_suggestion(s.pk, self.user)

    # ---- dismiss_suggestion ----

    def test_dismiss_marca_dismissed(self):
        s = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )
        dismiss_suggestion(s.pk, self.user)
        s.refresh_from_db()
        self.assertEqual(s.status, "dismissed")
        self.assertEqual(s.resolved_by, self.user)
        self.assertIsNotNone(s.resolved_at)
        # não cria Rate
        self.assertEqual(Rate.objects.filter(operacao="TEST_OP").count(), 1)


class LearningEngineSuggestionViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="view_user")
        self.user.set_password("segredo123")
        self.user.save()
        self.rate = Rate.objects.create(
            operacao="TEST_OP", rate_hh=Decimal("100.00"),
            rate_hm=Decimal("0.00"), valid_from=date(2025, 1, 1),
        )

    def _make_suggestion(self):
        return RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )

    def test_lista_get_200(self):
        self.assertTrue(self.client.login(username="view_user", password="segredo123"))
        resp = self.client.get("/engenharia/sugestoes/")
        self.assertEqual(resp.status_code, 200)

    def test_lista_unauthenticated_redirect(self):
        resp = self.client.get("/engenharia/sugestoes/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_apply_post_cria_rate_e_redireciona(self):
        self.assertTrue(self.client.login(username="view_user", password="segredo123"))
        s = self._make_suggestion()
        resp = self.client.post(f"/engenharia/sugestoes/{s.pk}/aplicar/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/engenharia/sugestoes/")
        s.refresh_from_db()
        self.assertEqual(s.status, "accepted")
        novo = Rate.objects.vigente("TEST_OP")
        self.assertEqual(novo.rate_hh, Decimal("115.00"))

    def test_dismiss_post_redireciona(self):
        self.assertTrue(self.client.login(username="view_user", password="segredo123"))
        s = self._make_suggestion()
        resp = self.client.post(f"/engenharia/sugestoes/{s.pk}/descartar/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/engenharia/sugestoes/")
        s.refresh_from_db()
        self.assertEqual(s.status, "dismissed")
