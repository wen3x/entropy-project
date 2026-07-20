import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import User


class RecaptchaLoginForm(AuthenticationForm):
    """Форма входа с проверкой reCAPTCHA v3.
    Токен reCAPTCHA передаётся через скрытое поле g-recaptcha-response.
    """
    g_recaptcha_response = forms.CharField(
        widget=forms.HiddenInput(), required=False
    )

    def clean(self):
        cleaned = super().clean()
        # Проверяем reCAPTCHA прямо в форме (self.request доступен)
        token = self.cleaned_data.get('g_recaptcha_response', '')
        if token:
            from django.conf import settings
            import json
            import urllib.request, urllib.parse
            secret = getattr(settings, 'RECAPTCHA_SECRET_KEY', '')
            if secret:
                try:
                    data = urllib.parse.urlencode({
                        'secret': secret,
                        'response': token,
                    }).encode()
                    req = urllib.request.Request(
                        'https://www.google.com/recaptcha/api/siteverify',
                        data=data,
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        result = json.loads(resp.read().decode())
                    if not result.get('success', False) or result.get('score', 0) < 0.5:
                        raise forms.ValidationError("Проверка reCAPTCHA не пройдена. Попробуйте ещё раз.")
                except Exception:
                    raise forms.ValidationError("Ошибка проверки reCAPTCHA. Попробуйте ещё раз.")
        return cleaned


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs={"placeholder": "your@email.com"}),
    )
    email_notifications = forms.BooleanField(
        required=False,
        initial=True,
        label="Рассылать уведомления на почту",
        help_text="Уведомления о новых комментариях, лайках и т.д.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username:
            username = username.lower()
            if not re.match(r"^[a-z0-9_-]+$", username):
                raise ValidationError(
                    "Латиница, цифры, дефис и подчёркивание. Без пробелов и русского."
                )
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower().strip()
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError("Этот email уже зарегистрирован.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.email_notifications = self.cleaned_data.get("email_notifications", True)
        if commit:
            user.save()
        return user


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(
        label="Текущий пароль",
        widget=forms.PasswordInput(),
        required=True,
    )
    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(),
        required=True,
    )
    new_password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(),
        required=True,
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        pwd = self.cleaned_data["current_password"]
        if not self.user.check_password(pwd):
            raise ValidationError("Неверный текущий пароль.")
        return pwd

    def clean_new_password2(self):
        p1 = self.cleaned_data.get("new_password1")
        p2 = self.cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Пароли не совпадают.")
        if p1:
            from django.contrib.auth.password_validation import validate_password
            try:
                validate_password(p1, user=self.user)
            except ValidationError as e:
                raise ValidationError("; ".join(e.messages))
        return p2

    def save(self):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save(update_fields=["password"])


class ChangeEmailForm(forms.Form):
    current_email = forms.EmailField(
        label="Текущий email",
        required=True,
    )
    new_email = forms.EmailField(
        label="Новый email",
        required=True,
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_email(self):
        email = self.cleaned_data["current_email"].lower().strip()
        if email != self.user.email.lower():
            raise ValidationError("Неверный текущий email.")
        return email

    def clean_new_email(self):
        email = self.cleaned_data["new_email"].lower().strip()
        if email == self.user.email.lower():
            raise ValidationError("Новый email совпадает с текущим.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Этот email уже используется.")
        return email
