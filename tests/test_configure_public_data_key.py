"""Manual key setup uses synthetic values only."""

import pytest
from dotenv import dotenv_values

from scripts.configure_public_data_key import save_key


def test_save_key_preserves_other_collector_settings(tmp_path):
    env_path = tmp_path / "collector.env"
    env_path.write_text("SUPABASE_DB_URL=postgresql://example.invalid/db\n", encoding="utf-8")
    save_key("syntheticDecodingKey0123456789", tmp_path)
    values = dotenv_values(env_path)
    assert values["SUPABASE_DB_URL"] == "postgresql://example.invalid/db"
    assert values["DATA_GO_KR_SERVICE_KEY"] == "syntheticDecodingKey0123456789"


@pytest.mark.parametrize("key", ["", "short", "invalid key with spaces"])
def test_rejects_invalid_key_without_writing(tmp_path, key):
    with pytest.raises(ValueError):
        save_key(key, tmp_path)
    assert not (tmp_path / "collector.env").exists()
