from django.core.management.base import BaseCommand
from crm.models import Lead


class Command(BaseCommand):
    help = "Delete only records explicitly marked as demo."

    def handle(self, *args, **options):
        count, _ = Lead.objects.filter(is_demo=True).delete()
        self.stdout.write(f"Удалено демонстрационных объектов: {count}.")

