from django import forms

from .models import Comment, Node, Post

INPUT = "entropy-input w-full px-3 py-2 text-sm"


class PostForm(forms.ModelForm):
    """Форма создания поста с поддержкой Cloudinary медиа.
    Поля image_file/audio_file/gif_file — загрузка файлов напрямую в Cloudinary.
    Поля image/audio/gif — ручной ввод URL (если файл не загружен).
    """
    image_file = forms.FileField(
        required=False,
        label="Изображение",
        widget=forms.FileInput(attrs={"class": INPUT, "accept": "image/*"}),
    )
    audio_file = forms.FileField(
        required=False,
        label="Аудио",
        widget=forms.FileInput(attrs={"class": INPUT, "accept": "audio/*"}),
    )
    gif_file = forms.FileField(
        required=False,
        label="GIF",
        widget=forms.FileInput(attrs={"class": INPUT, "accept": "image/gif"}),
    )

    class Meta:
        model = Post
        fields = ("title", "content", "image_file", "image", "audio_file", "audio", "gif_file", "gif")
        labels = {
            "title": "Заголовок",
            "content": "Текст",
            "image": "Или вставьте URL изображения",
            "audio": "Или вставьте URL аудио",
            "gif": "Или вставьте URL GIF",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT}),
            "content": forms.Textarea(attrs={"rows": 6, "class": INPUT}),
            "image": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://res.cloudinary.com/.../image.jpg"}),
            "audio": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://res.cloudinary.com/.../audio.mp3"}),
            "gif": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://res.cloudinary.com/.../animation.gif"}),
        }
        help_texts = {
            "image": "Загрузите файл или вставьте Cloudinary URL",
            "audio": "Загрузите файл или вставьте Cloudinary URL",
            "gif": "Загрузите файл или вставьте Cloudinary URL",
        }


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
