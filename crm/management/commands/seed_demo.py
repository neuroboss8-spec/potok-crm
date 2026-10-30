from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from crm.models import Activity, Lead
from crm.services import add_lead_tag, create_lead


class Command(BaseCommand):
    help = "Create or refresh twelve clearly marked fictional demo leads."

    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("DEMO_MODE=1 required. Refusing to seed a non-demo instance.")
        sample = [
            ("Анна Примерова", "email", "anna@example.com", "У нас мастерская керамики в Казани. Нужен лендинг на 5–6 блоков с каталогом работ, формой записи на мастер-класс и заявкой в Telegram. Фото и тексты подготовим сами, домен уже есть. Хотим запуститься к началу следующего месяца — подскажите сроки и что понадобится от нас."),
            ("Илья Макетов", "email", "ilya@example.com", "У дилерского центра две точки в Екатеринбурге. Яндекс Директ ведём сами, но много нецелевых запросов. Нужны аудит кампаний, чистка семантики и план теста на месяц. На рекламу готовы выделять около 120 000 ₽ в месяц; этот бюджет оплачиваем отдельно. Сколько будут стоить настройка и ведение?"),
            ("Мария Тестова", "email", "maria@example.com", "На сайте онлайн-школы заявки с квиза вручную переносят в amoCRM. Нужно передавать имя, телефон, выбранный курс и UTM-метки, создавать сделку и уведомлять менеджера в Telegram. Дубли проверять по телефону. Доступы к сайту и CRM подготовим после оценки объёма и сроков."),
            ("Павел Демин", "email", "pavel@example.com", "Готовим ноябрьский набор на курс по графическому дизайну. Нужен лендинг с программой, преподавателями, тарифами, FAQ и формой заявки, плюс Яндекс Метрика. Онлайн-оплату пока подключать не нужно. Контент есть, хотим понять стоимость и успеем ли запуститься за три недели."),
            ("София Учебная", "email", "sofia@example.com", "Три месяца запускаем рекламу в Директе. Заявок стало больше, но менеджеры жалуются на повторы и нецелевые обращения. Просим разобрать поисковые запросы, цели в Метрике и стоимость заявки, затем составить план оптимизации. Доступы готовы предоставить после согласования работ."),
            ("Денис Контуров", "email", "denis@example.com", "Формы с двух лендингов сейчас приходят на общий email. Хотим передавать заявки в amoCRM вместе с UTM-метками, адресом страницы и источником, создавать сделку в нужной воронке и уведомлять ответственного. Сайт на Tilda, CRM уже настроена. Нужны смета и срок интеграции."),
            ("Елена Заявкина", "email", "elena@example.com", "Готовим к публикации около 40 карточек в каталоге клиники. До запуска нужен SEO-аудит: проверить дубли title и H1, индексацию фильтров, микроразметку и перелинковку. Техкоманда у нас своя, поэтому просим список ошибок с приоритетами и понятными заданиями на исправление."),
            ("Роман Верный", "email", "roman@example.com", "Менеджеры каждый день переносят заказы из 1С в Excel, а потом вручную заводят сделки в amoCRM. Нужно настроить обмен по номеру заказа, переносить статус и ответственного, не создавать дубли и сообщать об ошибке синхронизации. Можем показать текущую схему и тестовую выгрузку."),
            ("Ольга Короткая", "email", "olga@example.com", "У студии пилатеса в Новосибирске через месяц открывается вторая площадка. Нужен первый месяц продвижения во ВКонтакте: контент-план, 8–10 публикаций, оформление сообщества и геореклама на новый район. На размещение готовы заложить ещё 60 000 ₽ отдельно от услуг. Хотим получать обращения в CRM."),
            ("Тимур Проектов", "email", "timur@example.com", "Компания продаёт инженерное оборудование, корпоративному сайту семь лет. Нужен редизайн примерно восьми страниц: адаптивная версия, сохранение URL и поискового трафика, формы с передачей заявок в CRM и Метрика. Часть текстов обновим сами. Просим расписать этапы, стоимость и поддержку после запуска."),
            ("Дарья Светлова", "email", "daria@example.com", "Запускаем доставку корпоративных обедов в Перми. Нужен лендинг с меню, условиями доставки и двумя формами: заказ для частного клиента и запрос КП для офиса. Трафик планируем вести из Директа, поэтому важно передавать заявки и UTM-метки в CRM. Меню и фотографии уже готовы."),
            ("Алексей Начальный", "email", "alex@example.com", "Развиваю мастерскую корпусной мебели и хочу понятнее сформулировать предложение для частных клиентов. Нужна консультация на полтора часа: выбрать приоритетный сегмент, уточнить оффер и наметить первый рекламный канал. После встречи хотелось бы получить короткий список гипотез и следующих действий."),
        ]
        tags = ["Сайт", "Реклама", "Автоматизация", "Дизайн", "Реклама", "Автоматизация", "SEO", "Автоматизация", "Реклама", "Сайт", "Сайт", "Консультация"]
        statuses = [
            Lead.Status.NEW, Lead.Status.QUALIFIED, Lead.Status.BRIEFING, Lead.Status.PROPOSAL_SENT,
            Lead.Status.NEGOTIATION, Lead.Status.IN_PROGRESS, Lead.Status.WAITING, Lead.Status.IN_PROGRESS,
            Lead.Status.WAITING, Lead.Status.CLOSED, Lead.Status.QUALIFIED, Lead.Status.LOST,
        ]
        # Plausible agency service fees in RUB; media budgets mentioned in briefs are separate.
        deal_amounts = ["125000.00", "45000.00", "100000.00", "85000.00", "55000.00", "100000.00", "45000.00", "165000.00", "45000.00", "380000.00", "110000.00", "18000.00"]
        follow_up_days = {0: 0, 1: 1, 2: 2, 4: 4, 5: 7, 6: 10, 7: 14, 10: 20}
        now = timezone.now()
        created_count = 0
        updated_count = 0
        for index, ((name, contact_type, contact, request), tag, deal_amount) in enumerate(zip(sample, tags, deal_amounts)):
            deal_amount = Decimal(deal_amount)
            existing = Lead.objects.filter(is_demo=True, name=name).first()
            if existing:
                if existing.request != request or existing.deal_amount != deal_amount:
                    existing.request = request
                    existing.deal_amount = deal_amount
                    existing.save(update_fields=["request", "deal_amount", "updated_at"])
                    updated_count += 1
                continue
            lead, _ = create_lead(
                data={"name": name, "contact_type": contact_type, "contact_value": contact, "request": request, "deal_amount": deal_amount},
                source=Lead.Source.MANUAL, tags=[tag], is_demo=True,
            )
            created_count += 1
            created_at = now - timedelta(days=(index * 3) % 14, hours=index % 6)
            next_contact_date = timezone.localdate() + timedelta(days=follow_up_days[index]) if index in follow_up_days else None
            Lead.objects.filter(pk=lead.pk).update(
                created_at=created_at,
                updated_at=created_at,
                status=statuses[index],
                next_contact_date=next_contact_date,
            )
            Activity.objects.filter(lead=lead, kind="created").update(created_at=created_at)
        self.stdout.write(self.style.SUCCESS(
            f"Создано демо-заявок: {created_count}; обновлено демо-заявок: {updated_count}. "
            "Бюджет на размещение отделён от суммы сделки за услуги."
        ))
