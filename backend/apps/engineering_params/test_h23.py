"""
Testes TDD H2.3 — Learning Engine (service + views).

Cobre os 24 cenários do motor de aprendizado de rates:
- LearningEngineServiceTests: generate_suggestions / apply_suggestion / dismiss_suggestion
- LearningEngineSuggestionViewTests: lista + aplicar + descartar + RBAC (HTTP)

Usa TenantTestCase: as tabelas de TENANT_APPS só existem no schema do tenant de teste.
Self-contained: cria Rate vigente e ActualRate no setUp / por teste.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import RequestFactory
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
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
        self.assertEqual(novo.valid_from, timezone.localdate())

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

    def test_confianca_borda_0_70_gera(self):
        """confidence=0.70 exato (==CONF_MINIMA) deve gerar — borda inclusiva."""
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.70"),
        )
        criadas = generate_suggestions()
        self.assertEqual(len(criadas), 1)
        self.assertEqual(RateSuggestion.objects.filter(status="pending").count(), 1)

    def test_rate_hh_zero_nao_gera(self):
        """Rate com rate_hh=0 é pulado (evita divisão por zero)."""
        self.rate.rate_hh = Decimal("0.00")
        self.rate.save()
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.80"),
        )
        self.assertEqual(generate_suggestions(), [])

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

    # ---- apply: convenções e edge cases ----

    def test_apply_rate_hm_zero(self):
        """Rate criado por apply tem rate_hm=0.00, não NULL."""
        s = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )
        apply_suggestion(s.pk, self.user)
        novo = Rate.objects.vigente("TEST_OP")
        self.assertEqual(novo.rate_hm, Decimal("0.00"))

    def test_apply_com_request_fecha_vigente_e_audita_origem_apontamento(self):
        """apply_suggestion(request=...) reusa o caminho de edição versionada da calibração
        (T2): fecha o Rate vigente (valid_until) em vez de deixar dois vigentes sobrepostos,
        e audita a mudança com origem='apontamento'."""
        s = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )
        antigo_pk = self.rate.pk
        request = RequestFactory().post(f"/engenharia/calibracao/sugestoes/{s.pk}/aceitar/")
        request.user = self.user

        apply_suggestion(s.pk, self.user, request=request)

        self.rate.refresh_from_db()
        self.assertEqual(self.rate.valid_until, timezone.localdate() - timedelta(days=1))

        novo = Rate.objects.vigente("TEST_OP")
        self.assertNotEqual(novo.pk, antigo_pk)
        self.assertEqual(novo.rate_hh, Decimal("115.00"))

        log = AccessLog.objects.get(action="rate_change", resource_id=str(novo.pk))
        self.assertEqual(log.metadata["origem"], "apontamento")
        self.assertEqual(log.metadata["operacao"], "TEST_OP")
        self.assertEqual(log.metadata["suggestion_id"], s.pk)

    def test_apply_sem_request_nao_audita(self):
        """Sem request (ex.: chamada programática), apply_suggestion não deve quebrar nem
        criar AccessLog — auditoria é opcional, versionamento não."""
        s = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )
        apply_suggestion(s.pk, self.user)
        self.assertFalse(AccessLog.objects.filter(action="rate_change").exists())

    def test_apply_mesmo_dia_idempotente(self):
        """Dois applies no mesmo dia → update_or_create, não IntegrityError."""
        s1 = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("115.00"),
            current_rate_hh=Decimal("100.00"), delta_pct=Decimal("15.00"),
            n_samples=25, confidence=Decimal("0.80"),
        )
        apply_suggestion(s1.pk, self.user)
        # Cria segunda sugestão e aplica no mesmo dia
        s2 = RateSuggestion.objects.create(
            operacao="TEST_OP", actual_mean_rate=Decimal("120.00"),
            current_rate_hh=Decimal("115.00"), delta_pct=Decimal("4.35"),
            n_samples=30, confidence=Decimal("0.85"),
        )
        apply_suggestion(s2.pk, self.user)  # não deve levantar IntegrityError
        novo = Rate.objects.vigente("TEST_OP")
        self.assertEqual(novo.rate_hh, Decimal("120.00"))


class LearningEngineSuggestionViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        # Engenheiro: pode aplicar/descartar sugestões
        self.eng = User.objects.create_user(username="engenheiro", password="segredo123")
        UserProfile.objects.create(user=self.eng, role=UserProfile.ROLE_ENGENHEIRO, crea_number="CREA-123")
        # Orçamentista: só pode visualizar
        self.orc = User.objects.create_user(username="orcamentista", password="segredo123")
        UserProfile.objects.create(user=self.orc, role=UserProfile.ROLE_ORCAMENTISTA)
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
        self.assertTrue(self.client.login(username="engenheiro", password="segredo123"))
        resp = self.client.get("/engenharia/sugestoes/")
        self.assertEqual(resp.status_code, 200)

    def test_lista_unauthenticated_redirect(self):
        resp = self.client.get("/engenharia/sugestoes/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_apply_post_cria_rate_e_redireciona(self):
        self.assertTrue(self.client.login(username="engenheiro", password="segredo123"))
        s = self._make_suggestion()
        resp = self.client.post(f"/engenharia/sugestoes/{s.pk}/aplicar/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/engenharia/sugestoes/")
        s.refresh_from_db()
        self.assertEqual(s.status, "accepted")
        novo = Rate.objects.vigente("TEST_OP")
        self.assertEqual(novo.rate_hh, Decimal("115.00"))

    def test_dismiss_post_redireciona(self):
        self.assertTrue(self.client.login(username="engenheiro", password="segredo123"))
        s = self._make_suggestion()
        resp = self.client.post(f"/engenharia/sugestoes/{s.pk}/descartar/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/engenharia/sugestoes/")
        s.refresh_from_db()
        self.assertEqual(s.status, "dismissed")

    def test_apply_orcamentista_403(self):
        """Orçamentista não pode modificar rates — recebe 403."""
        self.assertTrue(self.client.login(username="orcamentista", password="segredo123"))
        s = self._make_suggestion()
        resp = self.client.post(f"/engenharia/sugestoes/{s.pk}/aplicar/")
        self.assertEqual(resp.status_code, 403)
        s.refresh_from_db()
        self.assertEqual(s.status, "pending")

    def test_apply_sem_profile_barrado(self):
        """Usuário autenticado SEM UserProfile (não-membro do tenant) é barrado.

        Com TenantMembershipMiddleware, um usuário sem profile no schema ativo é
        deslogado e redirecionado ao login (302) antes de chegar à view.
        """
        sem_profile = User.objects.create_user(username="semProfile", password="segredo123")
        self.assertTrue(self.client.login(username="semProfile", password="segredo123"))
        s = self._make_suggestion()
        resp = self.client.post(f"/engenharia/sugestoes/{s.pk}/aplicar/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/login/")

    def test_apply_get_405(self):
        """GET no endpoint apply → 405 Method Not Allowed."""
        self.assertTrue(self.client.login(username="engenheiro", password="segredo123"))
        s = self._make_suggestion()
        resp = self.client.get(f"/engenharia/sugestoes/{s.pk}/aplicar/")
        self.assertEqual(resp.status_code, 405)

    def test_refresh_orcamentista_nao_gera(self):
        """POST refresh por orçamentista não deve criar sugestões."""
        from apps.production.models import ActualRate
        ActualRate.objects.create(
            operacao="TEST_OP", sample_count=25,
            mean_rate=Decimal("115.00"), confidence=Decimal("0.80"),
        )
        self.assertTrue(self.client.login(username="orcamentista", password="segredo123"))
        resp = self.client.post("/engenharia/sugestoes/", {"refresh": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(RateSuggestion.objects.count(), 0)

    def test_lista_orcamentista_pode_ver(self):
        """Orçamentista tem acesso de leitura à lista — GET 200."""
        self.assertTrue(self.client.login(username="orcamentista", password="segredo123"))
        resp = self.client.get("/engenharia/sugestoes/")
        self.assertEqual(resp.status_code, 200)
