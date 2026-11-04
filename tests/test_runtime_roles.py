from scripts.provision_runtime_roles import login_url


def test_pooler_login_url_keeps_tenant_and_escapes_password():
    source = "postgresql://postgres.project-ref:old@pooler.example:5432/postgres?sslmode=require"
    result = login_url(source, "yongin_analysis_login", "new@password")
    assert result == (
        "postgresql://yongin_analysis_login.project-ref:new%40password"
        "@pooler.example:5432/postgres?sslmode=require"
    )
    assert "old" not in result


def test_direct_login_url_without_pooler_tenant():
    result = login_url(
        "postgresql://postgres:old@db.example:5432/postgres",
        "yongin_collector_login", "safe-password",
    )
    assert result.startswith("postgresql://yongin_collector_login:safe-password@")
