from app.models import default_expires_at
from datetime import datetime, timedelta


def test_default_expires_at():
    expires_at = default_expires_at()
    assert isinstance(expires_at, datetime)
    assert expires_at > datetime.utcnow()
    assert (expires_at - datetime.utcnow()).days == 30
