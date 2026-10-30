import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the single Telegram bot long-polling process."

    def handle(self, *args, **options):
        if not settings.BOT_TOKEN:
            raise CommandError("BOT_TOKEN is empty; configure the separate demo bot token in .env.")
        from crm.telegram import run
        asyncio.run(run(settings.BOT_TOKEN))

