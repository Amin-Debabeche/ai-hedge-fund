from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from src.data.llm_cache import LLMCache, get_llm_cache


class DummySignal(BaseModel):
    signal: str
    confidence: float


@pytest.fixture
def cache(tmp_path):
    return LLMCache(db_path=tmp_path / "llm_cache.sqlite3")


class TestMakeKey:
    """Test cache key derivation."""

    def test_same_inputs_produce_same_key(self, cache):
        key1 = cache.make_key(
            agent_name="warren_buffett_agent",
            model_name="gpt-4.1",
            model_provider="OPENAI",
            pydantic_model_name="WarrenBuffettSignal",
            prompt="Analyze AAPL",
        )
        key2 = cache.make_key(
            agent_name="warren_buffett_agent",
            model_name="gpt-4.1",
            model_provider="OPENAI",
            pydantic_model_name="WarrenBuffettSignal",
            prompt="Analyze AAPL",
        )
        assert key1 == key2

    @pytest.mark.parametrize(
        "overrides",
        [
            {"agent_name": "other_agent"},
            {"model_name": "gpt-4o"},
            {"model_provider": "ANTHROPIC"},
            {"pydantic_model_name": "OtherSignal"},
            {"prompt": "Analyze MSFT"},
        ],
    )
    def test_different_inputs_produce_different_keys(self, cache, overrides):
        base = dict(
            agent_name="warren_buffett_agent",
            model_name="gpt-4.1",
            model_provider="OPENAI",
            pydantic_model_name="WarrenBuffettSignal",
            prompt="Analyze AAPL",
        )
        key1 = cache.make_key(**base)
        key2 = cache.make_key(**{**base, **overrides})
        assert key1 != key2

    def test_serializes_chat_message_list_prompts(self, cache):
        system = MagicMock(type="system", content="You are an analyst")
        human = MagicMock(type="human", content="Analyze AAPL")
        key_from_messages = cache.make_key(
            agent_name="a",
            model_name="m",
            model_provider="OPENAI",
            pydantic_model_name="S",
            prompt=[system, human],
        )
        key_from_string = cache.make_key(
            agent_name="a",
            model_name="m",
            model_provider="OPENAI",
            pydantic_model_name="S",
            prompt="system: You are an analyst\nhuman: Analyze AAPL",
        )
        assert key_from_messages == key_from_string

    def test_serializes_chat_prompt_value(self, cache):
        message = MagicMock(type="human", content="Analyze AAPL")
        prompt_value = MagicMock()
        prompt_value.to_messages.return_value = [message]
        key = cache.make_key(
            agent_name="a",
            model_name="m",
            model_provider="OPENAI",
            pydantic_model_name="S",
            prompt=prompt_value,
        )
        expected = cache.make_key(
            agent_name="a",
            model_name="m",
            model_provider="OPENAI",
            pydantic_model_name="S",
            prompt="human: Analyze AAPL",
        )
        assert key == expected


class TestGetSet:
    """Test storing and retrieving cached responses."""

    def test_returns_none_for_missing_key(self, cache):
        assert cache.get("nonexistent") is None

    def test_set_then_get_roundtrips(self, cache):
        key = cache.make_key(
            agent_name="a", model_name="m", model_provider="OPENAI", pydantic_model_name="S", prompt="p"
        )
        payload = {"signal": "bullish", "confidence": 0.8}
        cache.set(
            key, payload, agent_name="a", model_name="m", model_provider="OPENAI", pydantic_model_name="S"
        )
        assert cache.get(key) == payload

    def test_set_overwrites_existing_key(self, cache):
        key = "k"
        cache.set(
            key, {"signal": "bullish"}, agent_name="a", model_name="m", model_provider="OPENAI", pydantic_model_name="S"
        )
        cache.set(
            key, {"signal": "bearish"}, agent_name="a", model_name="m", model_provider="OPENAI", pydantic_model_name="S"
        )
        assert cache.get(key) == {"signal": "bearish"}

    def test_persists_across_instances_on_same_db_path(self, tmp_path):
        db_path = tmp_path / "shared.sqlite3"
        cache1 = LLMCache(db_path=db_path)
        cache1.set(
            "k", {"signal": "bullish"}, agent_name="a", model_name="m", model_provider="OPENAI", pydantic_model_name="S"
        )

        cache2 = LLMCache(db_path=db_path)
        assert cache2.get("k") == {"signal": "bullish"}

    def test_clear_removes_all_entries(self, cache):
        cache.set(
            "k", {"signal": "bullish"}, agent_name="a", model_name="m", model_provider="OPENAI", pydantic_model_name="S"
        )
        cache.clear()
        assert cache.get("k") is None


class TestDisabled:
    """Test that the cache no-ops when disabled via env var."""

    def test_disabled_cache_never_stores(self, tmp_path):
        with patch.dict("os.environ", {"LLM_CACHE_ENABLED": "false"}):
            cache = LLMCache(db_path=tmp_path / "disabled.sqlite3")
            cache.set(
                "k", {"signal": "bullish"}, agent_name="a", model_name="m", model_provider="OPENAI", pydantic_model_name="S"
            )
            assert cache.get("k") is None
        assert not (tmp_path / "disabled.sqlite3").exists()


class TestGetLlmCache:
    """Test the global cache singleton."""

    def test_returns_cache_instance(self):
        assert isinstance(get_llm_cache(), LLMCache)

    def test_returns_same_instance(self):
        assert get_llm_cache() is get_llm_cache()


class TestCallLlmIntegration:
    """Test that call_llm reads/writes through the cache instead of re-invoking the LLM."""

    def test_second_call_with_same_inputs_skips_llm_invoke(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.utils.llm.get_llm_cache", lambda: LLMCache(db_path=tmp_path / "c.sqlite3"))

        from src.utils.llm import call_llm

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_llm
        mock_llm.invoke.return_value = DummySignal(signal="bullish", confidence=0.9)

        with (
            patch("src.utils.llm.get_model", return_value=mock_llm),
            patch("src.utils.llm.get_model_info", return_value=None),
        ):
            first = call_llm(prompt="Analyze AAPL", pydantic_model=DummySignal, agent_name="dummy_agent")
            second = call_llm(prompt="Analyze AAPL", pydantic_model=DummySignal, agent_name="dummy_agent")

        assert first == DummySignal(signal="bullish", confidence=0.9)
        assert second == DummySignal(signal="bullish", confidence=0.9)
        mock_llm.invoke.assert_called_once()

    def test_default_factory_fallback_is_never_cached(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.utils.llm.get_llm_cache", lambda: LLMCache(db_path=tmp_path / "c.sqlite3"))

        from src.utils.llm import call_llm

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_llm
        mock_llm.invoke.side_effect = RuntimeError("boom")
        fallback = DummySignal(signal="neutral", confidence=0.0)

        with (
            patch("src.utils.llm.get_model", return_value=mock_llm),
            patch("src.utils.llm.get_model_info", return_value=None),
        ):
            first = call_llm(
                prompt="Analyze AAPL",
                pydantic_model=DummySignal,
                agent_name="dummy_agent",
                max_retries=1,
                default_factory=lambda: fallback,
            )
            second = call_llm(
                prompt="Analyze AAPL",
                pydantic_model=DummySignal,
                agent_name="dummy_agent",
                max_retries=1,
                default_factory=lambda: fallback,
            )

        assert first == fallback
        assert second == fallback
        # Both calls hit the LLM since the failed attempt was never cached.
        assert mock_llm.invoke.call_count == 2
