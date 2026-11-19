import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from agent.core import llm, rag
from agent.core.llm import LLMResult, _to_openai, _complete_openai, kiem_khoa


def test_to_openai_messages_and_tools():
    messages = [
        {"role": "user", "content": "Xin chào"},
        {
            "role": "assistant",
            "content": "Tôi đang tìm kiếm...",
            "tool_calls": [{"id": "call_1", "name": "tra_cuu", "input": {"ma": "DH123"}}],
        },
        {
            "role": "tool",
            "results": [{"id": "call_1", "name": "tra_cuu", "output": {"trang_thai": "dang_giao"}}],
        },
    ]
    tools = [
        {
            "name": "tra_cuu",
            "description": "Tra cứu đơn hàng",
            "input_schema": {
                "type": "object",
                "properties": {"ma": {"type": "string"}},
                "required": ["ma"],
            },
        }
    ]

    oa_msgs, oa_tools = _to_openai(messages, tools)

    assert len(oa_msgs) == 3
    assert oa_msgs[0] == {"role": "user", "content": "Xin chào"}
    assert oa_msgs[1]["role"] == "assistant"
    assert oa_msgs[1]["content"] == "Tôi đang tìm kiếm..."
    assert len(oa_msgs[1]["tool_calls"]) == 1
    assert oa_msgs[1]["tool_calls"][0]["id"] == "call_1"
    assert oa_msgs[1]["tool_calls"][0]["function"]["name"] == "tra_cuu"
    assert json.loads(oa_msgs[1]["tool_calls"][0]["function"]["arguments"]) == {"ma": "DH123"}

    assert oa_msgs[2]["role"] == "tool"
    assert oa_msgs[2]["tool_call_id"] == "call_1"
    assert json.loads(oa_msgs[2]["content"]) == {"trang_thai": "dang_giao"}

    assert len(oa_tools) == 1
    assert oa_tools[0]["type"] == "function"
    assert oa_tools[0]["function"]["name"] == "tra_cuu"
    assert oa_tools[0]["function"]["description"] == "Tra cứu đơn hàng"
    assert oa_tools[0]["function"]["parameters"] == tools[0]["input_schema"]


import asyncio


def test_complete_openai_success(monkeypatch):
    mock_resp = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Dạ đơn hàng đang được giao ạ.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 15,
            "total_tokens": 65,
            "prompt_tokens_details": {"cached_tokens": 10},
        },
    }

    async def mock_post(self, url, headers=None, json=None):
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        assert json["model"] == "gpt-4o-mini"
        assert json["messages"][0]["role"] == "system"
        assert json["messages"][1]["role"] == "user"
        return httpx.Response(200, json=mock_resp)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    system = {"stable": "Bạn là CSKH", "volatile": ""}
    messages = [{"role": "user", "content": "Đơn hàng của tôi đâu?"}]

    res = asyncio.run(
        _complete_openai(
            system=system,
            messages=messages,
            model="gpt-4o-mini",
            max_tokens=100,
            tools=None,
            api_key="sk-test-key",
        )
    )

    assert isinstance(res, LLMResult)
    assert res.text == "Dạ đơn hàng đang được giao ạ."
    assert res.model == "gpt-4o-mini"
    assert res.tokens_in == 40  # 50 - 10 cache
    assert res.tokens_out == 15
    assert res.cache_read == 10
    assert res.cost_usd > 0
    assert res.stop_reason == "stop"


def test_complete_openai_tool_calls(monkeypatch):
    mock_resp = {
        "id": "chatcmpl-tool",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": "tra_cuu_don_hang",
                                "arguments": '{"ma_don": "DH999"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 30, "completion_tokens": 10},
    }

    async def mock_post(self, url, headers=None, json=None):
        return httpx.Response(200, json=mock_resp)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    system = {"stable": "CSKH", "volatile": ""}
    messages = [{"role": "user", "content": "Tra mã DH999"}]

    res = asyncio.run(
        _complete_openai(
            system=system,
            messages=messages,
            model="gpt-4o-mini",
            max_tokens=100,
            tools=[{"name": "tra_cuu_don_hang", "description": "", "input_schema": {}}],
            api_key="sk-test-key",
        )
    )

    assert len(res.tool_calls) == 1
    assert res.tool_calls[0]["id"] == "call_abc"
    assert res.tool_calls[0]["name"] == "tra_cuu_don_hang"
    assert res.tool_calls[0]["input"] == {"ma_don": "DH999"}


def test_kiem_khoa_openai(monkeypatch):
    mock_resp = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }

    async def mock_post(self, url, headers=None, json=None):
        assert headers["Authorization"] == "Bearer sk-test-kiem-khoa"
        return httpx.Response(200, json=mock_resp)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    ok, msg, ms = asyncio.run(
        kiem_khoa(
            provider_name="openai",
            api_key="sk-test-kiem-khoa",
            model="gpt-4o-mini",
        )
    )
    assert ok is True
    assert "gpt-4o-mini" in msg


def test_rag_embed_openai(monkeypatch):
    mock_resp = {
        "data": [
            {"index": 0, "embedding": [0.1] * 768},
            {"index": 1, "embedding": [0.2] * 768},
        ]
    }

    async def mock_post(self, url, headers=None, json=None):
        assert json["model"] == "text-embedding-3-small"
        assert json["dimensions"] == 768
        assert json["input"] == ["Đoạn 1", "Đoạn 2"]
        return httpx.Response(200, json=mock_resp)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    monkeypatch.setattr(llm, "provider", lambda: "openai")
    monkeypatch.setattr(llm, "_openai_key", lambda: "sk-test-rag")

    vecs = asyncio.run(rag._embed_openai(["Đoạn 1", "Đoạn 2"]))
    assert len(vecs) == 2
    assert len(vecs[0]) == 768
    assert len(vecs[1]) == 768


def test_loc_bo_markdown_anh():
    import re
    text = "Dạ đây là hình ảnh sản phẩm ạ:\n![Nước Tẩy Trang BLANICA](sandbox:/Users/test/img_00.jpg)\nGiá sản phẩm là 260.000đ nhé chị!"
    clean = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text).strip()
    assert clean == "Dạ đây là hình ảnh sản phẩm ạ:\n\nGiá sản phẩm là 260.000đ nhé chị!"
    assert "sandbox:" not in clean
    assert "img_00.jpg" not in clean
