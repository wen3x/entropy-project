import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import User


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
