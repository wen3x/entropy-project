from django import forms

from .models import Comment, Node, Post

INPUT = "entropy-input w-full px-3 py-2 text-sm"


MEDIA_TYPE_CHOICES = [
    ("", "Без медиа"),
    ("image", "Изображение"),
    ("gif", "GIF"),
    ("audio", "Аудио"),
]

MEDIA_SOURCE_CHOICES = [
    ("upload", "Загрузить файл"),
    ("url", "Вставить ссылку"),
]


class PostForm(forms.ModelForm):
    """Форма создания поста с поддержкой Cloudinary медиа и @упоминаний.
    Сначала выбирается тип медиа (изображение/GIF/аудио), потом способ (файл/ссылка).
    """
    media_type = forms.ChoiceField(
        choices=MEDIA_TYPE_CHOICES,
        required=False,
        label="Медиа",
        widget=forms.Select(attrs={"class": INPUT}),
    )
    media_source = forms.ChoiceField(
        choices=MEDIA_SOURCE_CHOICES,
        required=False,
        label="Способ",
        widget=forms.Select(attrs={"class": INPUT}),
    )
    media_file = forms.FileField(
        required=False,
        label="Файл",
        widget=forms.FileInput(attrs={"class": INPUT}),
    )
    media_url = forms.URLField(
        required=False,
        label="Ссылка",
        widget=forms.URLInput(attrs={"class": INPUT, "placeholder": "https://..."}),
    )

    class Meta:
        model = Post
        fields = ("title", "content",)
        labels = {
            "title": "Заголовок",
            "content": "Текст",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT}),
            "content": forms.Textarea(attrs={"rows": 6, "class": INPUT, "placeholder": "Текст поста... (@username — упомянуть пользователя)"}),
        }

    def clean(self):
        cleaned = super().clean()
        media_type = cleaned.get("media_type")
        media_source = cleaned.get("media_source")
        media_file = cleaned.get("media_file")
        media_url = cleaned.get("media_url")

        if media_type:
            if not media_source:
                self.add_error("media_source", "Выберите способ: загрузить файл или вставить ссылку.")
            elif media_source == "upload" and not media_file:
                self.add_error("media_file", "Загрузите файл или выберите «Вставить ссылку».")
            elif media_source == "url" and not media_url:
                self.add_error("media_url", "Вставьте ссылку или выберите «Загрузить файл».")

        return cleaned


class NodeForm(forms.ModelForm):
    """Форма для создания/редактирования узла."""
    class Meta:
        model = Node
        fields = ("slug", "name", "description", "avatar", "header")
        labels = {"slug": "URL узла", "name": "Название", "description": "Описание", "avatar": "Аватар (URL)", "header": "Шапка (URL)"}
        widgets = {
            "slug": forms.TextInput(attrs={"class": INPUT}),
            "name": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"rows": 3, "class": INPUT}),
            "avatar": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://res.cloudinary.com/.../avatar.png"}),
            "header": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://res.cloudinary.com/.../banner.png"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # При редактировании slug менять нельзя — это URL узла
        if self.instance and self.instance.pk:
            self.fields["slug"].disabled = True
            self.fields["slug"].help_text = "URL узла нельзя изменить после создания"


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("text",)
        labels = {"text": "Ваше мнение"}
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Ваш комментарий… (@username — упомянуть пользователя)",
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
