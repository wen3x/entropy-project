from django import forms

from .models import Comment, Post

INPUT = "entropy-input w-full px-3 py-2 text-sm"


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ("title", "content")
        labels = {"title": "Заголовок", "content": "Текст"}
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT}),
            "content": forms.Textarea(attrs={"rows": 6, "class": INPUT}),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("text",)
        labels = {"text": "Ваше мнение (один раз под постом)"}
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Ваш комментарий…",
                    "class": INPUT,
                }
            ),
        }


class ReplyForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("text",)
        labels = {"text": "Ответ"}
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Ответ на комментарий…",
                    "class": INPUT,
                }
            ),
        }
