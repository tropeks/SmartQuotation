"""Data sheet do PERMUTADOR COMPLETO — dimensões reais do projeto que recomputam o custo.

Fecha a crítica #1/#9: em vez de só replayar o seed, o orçamentista informa as dimensões
e o motor recomputa o peso geométrico (parametria de verdade). Os campos mapeiam para
labels de material do seed via to_dims_override().
"""
from django import forms

from apps.tema_templates.services import COSTABLE, LIGA_CHOICES

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
    # casco (paramétrico — recomputa peso das virolas + escala horas de solda/calandragem)
    comprimento_casco_mm = forms.FloatField(label="Comprimento da virola/casco (mm)", min_value=1)
    diametro_casco_mm = forms.FloatField(label="Diâmetro do casco (mm)", min_value=1)
    esp_casco_mm = forms.FloatField(label="Espessura da virola (mm)", min_value=0.1)
    # metalurgia (escala horas de caldeiraria/solda)
    classe_metalurgica = forms.ChoiceField(
        label="Classe metalúrgica", choices=LIGA_CHOICES, initial="CS")
    # mão de obra
    fator_correcao_mo = forms.FloatField(
        label="Fator de correção de MO", min_value=0.1, initial=1.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # choices como callable não é aceito direto em todas as versões — resolve aqui
        self.fields["designacao"].choices = [(d, d) for d in sorted(COSTABLE)]

    def to_dims_override(self):
        """Devolve (dims_override, fator_correcao_mo) a partir dos campos preenchidos."""
        cd = self.cleaned_data
        override = {
            LABEL_TUBOS: {
                "QUANTIDADE": cd["n_tubos"], "COMPR.": cd["comprimento_tubo_mm"],
                "OD": cd["od_tubo_mm"], "ESP.": cd["esp_tubo_mm"],
            },
            LABEL_VIROLA: {"COMPR.": cd["comprimento_casco_mm"]},
        }
        return override, cd["fator_correcao_mo"]
