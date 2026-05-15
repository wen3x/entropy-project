from django.core.management.base import BaseCommand

from accounts.quests import ensure_default_quests


class Command(BaseCommand):
    help = "Создаёт или обновляет стандартные квесты Entropy."

    def handle(self, *args, **options):
        ensure_default_quests()
        self.stdout.write(self.style.SUCCESS("Квесты загружены."))
