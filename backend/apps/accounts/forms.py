"""Forms do app accounts: login (session auth), edição de perfil e convite."""
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

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


class MemberInviteForm(forms.Form):
    email = forms.EmailField(
        label="E-mail",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "novo.membro@empresa.com"}),
    )
    full_name = forms.CharField(
        label="Nome completo",
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Nome do novo membro"}),
    )
    role = forms.ChoiceField(label="Papel", choices=UserProfile.ROLE)
    crea_number = forms.CharField(
        label="Número do CREA",
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Obrigatório para engenheiro"}),
    )
    crea_state = forms.CharField(
        label="UF do CREA",
        max_length=2,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "SP"}),
    )
    phone = forms.CharField(
        label="Telefone",
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "11999999999"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe um usuário com este e-mail.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        probe_user = User(username=cleaned_data["email"], email=cleaned_data["email"])
        profile = UserProfile(
            user=probe_user,
            full_name=cleaned_data["full_name"],
            role=cleaned_data["role"],
            crea_number=cleaned_data.get("crea_number", ""),
            crea_state=(cleaned_data.get("crea_state", "") or "").upper(),
            phone=cleaned_data.get("phone", ""),
            is_active=True,
            must_change_password=True,
        )
        try:
            profile.full_clean(exclude=["user"])
        except ValidationError as exc:
            for field, messages in exc.message_dict.items():
                for message in messages:
                    self.add_error(field, message)
        return cleaned_data


class MemberRoleChangeForm(forms.Form):
    """Reatribuição de papel RBAC de um membro existente. clean() delega a validação
    de domínio (engenheiro->CREA) para UserProfile.full_clean()."""

    role = forms.ChoiceField(label="Papel", choices=UserProfile.ROLE)
    crea_number = forms.CharField(label="Número do CREA", max_length=30, required=False)
    crea_state = forms.CharField(label="UF do CREA", max_length=2, required=False)
