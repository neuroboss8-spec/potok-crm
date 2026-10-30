from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError


class Command(BaseCommand):
    help = "Create the owner and reviewer without changing existing passwords."

    def handle(self, *args, **options):
        User = get_user_model()
        for username, role, staff in (("owner", "владельца", True), ("reviewer", "проверяющего", False)):
            user, created = User.objects.get_or_create(username=username, defaults={"is_staff": staff, "is_superuser": staff})
            if not created:
                self.stdout.write(f"{username}: пользователь уже есть; пароль и права не менялись.")
                continue
            password = getpass(f"Задайте пароль {role} (не менее 12 символов): ")
            confirmation = getpass("Повторите пароль: ")
            if password != confirmation or len(password) < 12:
                user.delete()
                raise CommandError("Пароли не совпадают или короче 12 символов. Запустите команду повторно.")
            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                user.delete()
                raise CommandError("Пароль не прошёл правила Django: " + " ".join(exc.messages)) from exc
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Создан пользователь {username}. Пароль не выводился."))
