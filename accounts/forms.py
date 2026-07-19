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
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username:
            username = username.lower()
            # Только латиница, цифры, дефис, подчёркивание
            if not re.match(r"^[a-z0-9_-]+$", username):
                raise ValidationError(
                    "Латиница, цифры, дефис и подчёркивание. Без пробелов и русского."
                )
        return username
