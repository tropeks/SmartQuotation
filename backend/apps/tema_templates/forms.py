"""Data sheet do PERMUTADOR COMPLETO — dimensões reais do projeto que recomputam o custo.

Fecha a crítica #1/#9: em vez de só replayar o seed, o orçamentista informa as dimensões
e o motor recomputa o peso geométrico (parametria de verdade). Os campos mapeiam para
labels de material do seed via to_dims_override().
"""
from django import forms

from apps.tema_templates.services import COSTABLE, LIGA_CHOICES, liga_choices

# label do material no seed → dimensões que o form sobrescreve
LABEL_TUBOS = "TUBOS DE TROCA TÉRMICA"
LABEL_VIROLA = "VIROLA"


class PermutadorDataSheetForm(forms.Form):
    designacao = forms.ChoiceField(
        label="Designação TEMA", choices=lambda: [(d, d) for d in sorted(COSTABLE)])
    # feixe (paramétrico — recomputa peso dos tubos)
    n_tubos = forms.IntegerField(label="Nº de tubos", min_value=1)
    comprimento_tubo_mm = forms.FloatField(label="Comprimento do tubo (mm)", min_value=1)
    od_tubo_mm = forms.FloatField(label="OD do tubo (mm)", min_value=1)
    esp_tubo_mm = forms.FloatField(label="Parede do tubo (mm)", min_value=0.1)
    # chicanas (paramétrico — escala horas do grupo chicanas)
    n_chicanas = forms.IntegerField(label="Nº de chicanas", min_value=1)
    # nº de passes dos tubos (escala os rasgos de partição do espelho/cabeçote)
    n_passes_tubos = forms.IntegerField(label="Nº de passes (tubos)", min_value=1, initial=2)
    # escopo de radiografia (B Wellington): multiplica o raio-X; ref do referencial = Total 100%
    rt_escopo = forms.ChoiceField(
        label="Escopo de radiografia", initial="Total",
        choices=[("Total", "Total (100%)"), ("Parcial", "Parcial (10%)"), ("Isento", "Isento")])
    # casco (paramétrico — recomputa peso das virolas + escala horas de solda/calandragem)
    comprimento_casco_mm = forms.FloatField(label="Comprimento da virola/casco (mm)", min_value=1)
    diametro_casco_mm = forms.FloatField(label="Diâmetro do casco (mm)", min_value=1)
    esp_casco_mm = forms.FloatField(label="Espessura da virola (mm)", min_value=0.1)
    # condições de projeto (A1): pressão+temperatura → espessura mínima ASME VIII UG-27 + alerta
    pressao_projeto_bar = forms.FloatField(label="Pressão de projeto (bar)", min_value=0,
                                           required=False)
    temperatura_projeto_c = forms.FloatField(label="Temperatura de projeto (°C)", required=False,
                                             initial=40)
    corrosao_mm = forms.FloatField(label="Sobrespessura de corrosão (mm)", required=False,
                                   initial=3.0, min_value=0)
    # densidade do fluido p/ coluna estática (ASME VIII UG-21); default água. Altura ≈ Ø do casco.
    densidade_fluido_kg_m3 = forms.FloatField(label="Densidade do fluido (kg/m³)", required=False,
                                              initial=1000, min_value=0)
    # metalurgia por lado (liga escala MO; densidade escala peso) — suporta bimetálico
    classe_feixe = forms.ChoiceField(
        label="Classe metalúrgica — feixe", choices=LIGA_CHOICES, initial="CS")
    classe_casco = forms.ChoiceField(
        label="Classe metalúrgica — casco", choices=LIGA_CHOICES, initial="CS")
    # fluido corrosivo (A2): se Tubos, cabeçote+espelhos herdam a metalurgia do feixe
    fluido_corrosivo = forms.ChoiceField(
        label="Fluido corrosivo", initial="Tubos",
        choices=[("Tubos", "Tubos"), ("Casco", "Casco"), ("Ambos", "Ambos")])
    # mão de obra
    fator_correcao_mo = forms.FloatField(
        label="Fator de correção de MO", min_value=0.1, initial=1.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # choices como callable não é aceito direto em todas as versões — resolve aqui
        self.fields["designacao"].choices = [(d, d) for d in sorted(COSTABLE)]
        # classes metalúrgicas do cadastro de ligas do tenant (fallback nas constantes)
        ligas = liga_choices()
        self.fields["classe_feixe"].choices = ligas
        self.fields["classe_casco"].choices = ligas

    def to_dims_override(self):
        """Devolve (dims_override, fator_correcao_mo) a partir dos campos preenchidos."""
        from apps.tema_templates.services import reference_inputs

        cd = self.cleaned_data
        ref = reference_inputs(cd["designacao"])
        ref_d = ref.get("diametro_casco_mm") or cd["diametro_casco_mm"]
        largura_ratio = float(cd["diametro_casco_mm"]) / float(ref_d)
        override = {
            LABEL_TUBOS: {
                "QUANTIDADE": cd["n_tubos"], "COMPR.": cd["comprimento_tubo_mm"],
                "OD": cd["od_tubo_mm"], "ESP.": cd["esp_tubo_mm"],
            },
            LABEL_VIROLA: {
                "COMPR.": cd["comprimento_casco_mm"],
                "ESP.": cd["esp_casco_mm"],
                "_LARGURA_RATIO": largura_ratio,
            },
        }
        return override, cd["fator_correcao_mo"]
