"""Data sheet do feixe tubular — campos que o orçamentista preenche."""
from django import forms

from apps.accounts.models import UserProfile
from apps.quotations.models import Customer

TIPO = [("TUBO RETO", "Tubo Reto"), ("TUBO U", "Tubo U")]
OD_TUBO = [('3/4"', '3/4"'), ('1"', '1"'), ('1.1/4"', '1.1/4"'), ('5/8"', '5/8"')]
BWG = [(f"BWG {n}", f"BWG {n}") for n in (12, 13, 14, 16, 18)]


class FeixeDataSheetForm(forms.Form):
    title = forms.CharField(label="Título da cotação", max_length=500)
    customer_name = forms.CharField(label="Cliente", max_length=255)
    tipo = forms.ChoiceField(label="Tipo de feixe", choices=TIPO)
    # tubos
    n_tubos = forms.IntegerField(label="Nº de tubos", min_value=1)
    tubo_material = forms.CharField(label="Material do tubo", max_length=50)
    tubo_od_spec = forms.ChoiceField(label="OD do tubo", choices=OD_TUBO)
    tubo_wall_spec = forms.ChoiceField(label="Parede (BWG)", choices=BWG)
    tubo_comp_mm = forms.FloatField(label="Comprimento (mm)")
    # espelhos
    espelho_material = forms.CharField(label="Material do espelho", max_length=50)
    espelho_od_mm = forms.FloatField(label="OD espelho fixo (mm)")
    espelho_flutuante_od_mm = forms.FloatField(label="OD espelho flutuante (mm)")
    espelho_esp_bruta_mm = forms.FloatField(label="Espessura espelho (mm)")
    # chicanas
    chicana_qty = forms.IntegerField(label="Nº de chicanas", min_value=0)
    chicana_od_mm = forms.FloatField(label="OD chicana (mm)")
    chicana_esp_mm = forms.FloatField(label="Espessura chicana (mm)")
    chicana_cut_remaining_mm = forms.FloatField(label="Corte chicana — altura restante (mm)")
    # tirantes
    tirante_qty = forms.IntegerField(label="Nº de tirantes", min_value=0)
    # config
    teste_hidrostatico = forms.BooleanField(label="Teste hidrostático", required=False)
    tratamento_termico = forms.BooleanField(label="Tratamento térmico", required=False)
    inspecao_q = forms.BooleanField(label='Inspeção tipo "Q"', required=False)

    _INPUT_KEYS = (
        "tipo", "n_tubos", "tubo_material", "tubo_od_spec", "tubo_wall_spec", "tubo_comp_mm",
        "espelho_material", "espelho_od_mm", "espelho_flutuante_od_mm", "espelho_esp_bruta_mm",
        "chicana_qty", "chicana_od_mm", "chicana_esp_mm", "chicana_cut_remaining_mm",
        "tirante_qty", "teste_hidrostatico", "tratamento_termico", "inspecao_q",
    )

    @classmethod
    def initial_from_quotation(cls, quotation) -> dict:
        """Pré-preenche o form com os inputs de uma cotação existente (edição/revisão)."""
        data = dict(quotation.inputs or {})
        data["title"] = quotation.title
        data["customer_name"] = quotation.customer.company_name if quotation.customer_id else ""
        return data

    def to_inputs_dict(self) -> dict:
        cd = self.cleaned_data
        d = {k: cd[k] for k in self._INPUT_KEYS if k in cd}
        # tubo_od_mm derivado do OD spec (mm) para os ajustes do motor
        from pricing_engine.dimensions import tube_od_mm
        try:
            d["tubo_od_mm"] = tube_od_mm(cd["tubo_od_spec"])
        except Exception:
            pass
        return d


class QuotationEntryForm(forms.Form):
    customer = forms.ModelChoiceField(label="Cliente", queryset=Customer.objects.none(), empty_label="Selecione")
    title = forms.CharField(label="Título", max_length=500)
    description = forms.CharField(
        label="Descrição",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "style": "min-height:96px;"}),
    )
    valid_until = forms.DateField(
        label="Válido até",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    delivery_weeks = forms.IntegerField(label="Prazo de entrega (semanas)", required=False, min_value=1)
    payment_terms = forms.CharField(
        label="Condições de pagamento",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "style": "min-height:96px;"}),
    )
    engineer_responsavel = forms.ModelChoiceField(
        label="Engenheiro responsável",
        queryset=UserProfile.objects.none(),
        required=False,
        empty_label="Selecione",
    )

    def __init__(self, *args, customer_queryset=None, engineer_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = (
            customer_queryset if customer_queryset is not None else Customer.objects.order_by("company_name")
        )
        self.fields["engineer_responsavel"].queryset = (
            engineer_queryset
            if engineer_queryset is not None
            else UserProfile.objects.filter(role=UserProfile.ROLE_ENGENHEIRO, is_active=True).select_related("user")
        )


class CustomerQuickForm(forms.ModelForm):
    """Cadastro rápido de cliente (modal na tela de Nova Cotação).

    Campos essenciais do brief: Razão Social + Contato + E-mail obrigatórios;
    CNPJ e Telefone opcionais (com máscara no front). A obrigatoriedade de
    contact_name/email é imposta aqui (no model são blank=True para dados legados).
    """

    class Meta:
        model = Customer
        fields = ["company_name", "cnpj", "contact_name", "email", "phone"]
        labels = {
            "company_name": "Razão Social",
            "cnpj": "CNPJ",
            "contact_name": "Contato",
            "email": "E-mail",
            "phone": "Telefone",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company_name"].required = True
        self.fields["contact_name"].required = True
        self.fields["email"].required = True
        self.fields["cnpj"].required = False
        self.fields["phone"].required = False
