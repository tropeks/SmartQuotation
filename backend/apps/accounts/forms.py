"""Forms do app accounts: login (session auth) e edição de UserProfile."""
from django import forms

from apps.accounts.models import UserProfile


class LoginForm(forms.Form):
    """Login por username ou e-mail + senha. Autenticação acontece na view."""
    identifier = forms.CharField(
        label="Usuário ou e-mail",
        max_length=254,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class UserProfileForm(forms.ModelForm):
    """Edição do perfil. clean() do modelo cobre a regra engenheiro->CREA."""

    class Meta:
        model = UserProfile
        fields = ["full_name", "role", "crea_number", "crea_state", "phone", "is_active"]
