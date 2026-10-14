from sqlalchemy.engine import make_url

from app.database import is_postgres, normalize_url


def test_postgres_prefixes_select_psycopg():
    assert normalize_url("postgres://u:p@h:5432/db").startswith("postgresql+psycopg://")
    assert normalize_url("postgresql://u:p@h:5432/db").startswith("postgresql+psycopg://")
    assert normalize_url("sqlite:///./x.db") == "sqlite:///./x.db"
    assert is_postgres("postgres://u:p@h/db") and not is_postgres("sqlite:///x.db")


def test_unencoded_special_characters_in_password_are_handled():
    raw = "postgresql://postgres.abcd:pa@ss!w:rd/x#y@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    url = make_url(normalize_url(raw))
    assert url.password == "pa@ss!w:rd/x#y"
    assert url.username == "postgres.abcd"
    assert url.host == "aws-0-ap-south-1.pooler.supabase.com" and url.port == 5432 and url.database == "postgres"


def test_already_encoded_password_is_not_double_encoded():
    url = make_url(normalize_url("postgresql://u:pa%40ss@h:5432/db"))
    assert url.password == "pa@ss"
