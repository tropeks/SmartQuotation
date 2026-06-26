from decimal import Decimal
from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase as TestCase
from apps.engineering_params.models import Rate, RateSuggestion
from apps.production.models import ActualRate
from apps.engineering_params.services import generate_suggestions, apply_suggestion, dismiss_suggestion

User = get_user_model()

class ServicesTests(TestCase):
    def setUp(self):
        from datetime import date
        self.user = User.objects.create(username='test')
        self.rate = Rate.objects.create(
            operacao='TEST_OP', rate_hh=Decimal('100.00'), rate_hm=Decimal('0.00'), valid_from=date(2025, 1, 1)
        )
        
    def test_generate_suggestions(self):
        ActualRate.objects.create(
            operacao='TEST_OP',
            sample_count=25,
            mean_rate=Decimal('110.00'),
            confidence=Decimal('0.80')
        )
        suggs = generate_suggestions()
        self.assertEqual(len(suggs), 1)
        self.assertEqual(suggs[0].operacao, 'TEST_OP')
        self.assertEqual(suggs[0].delta_pct, Decimal('10.00'))
        
    def test_generate_suggestions_idempotent(self):
        ActualRate.objects.create(
            operacao='TEST_OP', sample_count=25, mean_rate=Decimal('110.00'), confidence=Decimal('0.80')
        )
        generate_suggestions()
        suggs = generate_suggestions()
        self.assertEqual(len(suggs), 0)
        self.assertEqual(RateSuggestion.objects.count(), 1)
        
    def test_apply_suggestion(self):
        sugg = RateSuggestion.objects.create(
            operacao='TEST_OP', actual_mean_rate=Decimal('110.00'), current_rate_hh=Decimal('100.00'),
            delta_pct=Decimal('10.00'), n_samples=25, confidence=Decimal('0.80')
        )
        apply_suggestion(sugg.pk, self.user)
        sugg.refresh_from_db()
        self.assertEqual(sugg.status, 'accepted')
        self.assertEqual(sugg.resolved_by, self.user)
        
        new_rate = Rate.objects.vigente('TEST_OP')
        self.assertEqual(new_rate.rate_hh, Decimal('110.00'))
        
    def test_dismiss_suggestion(self):
        sugg = RateSuggestion.objects.create(
            operacao='TEST_OP', actual_mean_rate=Decimal('110.00'), current_rate_hh=Decimal('100.00'),
            delta_pct=Decimal('10.00'), n_samples=25, confidence=Decimal('0.80')
        )
        dismiss_suggestion(sugg.pk, self.user)
        sugg.refresh_from_db()
        self.assertEqual(sugg.status, 'dismissed')
        self.assertEqual(sugg.resolved_by, self.user)

    def test_generate_suggestions_clamps_extreme_delta(self):
        ActualRate.objects.create(
            operacao='TEST_OP',
            sample_count=25,
            mean_rate=Decimal('5000000.00'),
            confidence=Decimal('0.80')
        )
        suggs = generate_suggestions()
        self.assertEqual(len(suggs), 1)
        self.assertEqual(suggs[0].delta_pct, Decimal('9999.99'))
