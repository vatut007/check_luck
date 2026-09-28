import factory
from django.contrib.auth import get_user_model
from django.utils import timezone

from receipts.models import Receipt, ReceiptStatus


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")


class ReceiptFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Receipt

    fn = factory.Sequence(lambda n: str(9000000000000000 + n).zfill(16)[-16:])
    fd = factory.Sequence(lambda n: str(n + 1))
    fp = factory.Sequence(lambda n: str(n + 1))
    purchased_at = factory.LazyFunction(timezone.now)
    amount = "1500.00"
    status = ReceiptStatus.PENDING
    user = factory.SubFactory(UserFactory)
