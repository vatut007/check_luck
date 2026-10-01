import pytest

from receipts.errors import DomainError
from receipts.photos import PhotoError
from receipts.qr import QrParseError
from receipts.services import DrawError, DuplicateReceiptError, InvalidTransitionError
from receipts.validators import ValidationError

DOMAIN_ERROR_SUBCLASSES = [
    ValidationError,
    QrParseError,
    PhotoError,
    DuplicateReceiptError,
    InvalidTransitionError,
    DrawError,
]


class TestDomainError:
    @pytest.mark.parametrize("error_class", DOMAIN_ERROR_SUBCLASSES)
    def test_is_a_domain_error(self, error_class):
        assert issubclass(error_class, DomainError)

    @pytest.mark.parametrize("error_class", DOMAIN_ERROR_SUBCLASSES)
    def test_exposes_message_attribute(self, error_class):
        exc = error_class("что-то пошло не так")
        assert exc.message == "что-то пошло не так"
        assert str(exc) == "что-то пошло не так"
