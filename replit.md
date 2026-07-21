# Entropy

Русскоязычный Django-форум, где посты живут ограниченное время (7 дней).

## Стек

- Python 3.12+ / Django 5.2
- SQLite (dev) / PostgreSQL (prod)
- Tailwind CSS (CDN)
- WhiteNoise (статика)
- Cloudinary (медиа, опционально)

## Запуск

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Минимально необходима переменная `SECRET_KEY` в `.env`.

## User preferences

- Не коммитить каждое действие по отдельности — накапливать изменения и делать один коммит в конце.
- Сообщения коммитов писать на русском языке.
- Не упоминать Replit в коммитах и сообщениях.
