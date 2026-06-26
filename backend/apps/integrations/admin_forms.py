"""
Formulários de admin para configs de integração com segredos.

Os campos de credencial (password/token/app_key/app_secret) são write-only no admin:
renderizam vazios (PasswordInput, render_value=False) e, se submetidos em branco,
mantêm o valor já gravado. Assim o segredo nunca é exibido em cleartext na tela de
edição e continua rotacionável.
"""
from django import forms


def secret_config_form(model_cls, secret_fields):
    """Fábrica de ModelForm que mascara `secret_fields` do modelo `model_cls`."""
    secret_fields = tuple(secret_fields)

    class _SecretConfigForm(forms.ModelForm):
        class Meta:
            model = model_cls
            fields = "__all__"
            widgets = {
                name: forms.PasswordInput(render_value=False) for name in secret_fields
            }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for name in secret_fields:
                if name in self.fields:
                    self.fields[name].required = False
                    self.fields[name].help_text = (
                        "Deixe em branco para manter o valor atual; preencha para rotacionar."
                    )

        def clean(self):
            cleaned = super().clean()
            for name in secret_fields:
                if not cleaned.get(name):
                    # mantém o segredo já gravado quando o campo vem vazio
                    cleaned[name] = getattr(self.instance, name, "") or ""
            return cleaned

    return _SecretConfigForm
