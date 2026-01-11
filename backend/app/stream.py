import functools
from typing import Any, AsyncIterator, Dict, Optional, Sequence, Union

import orjson
import structlog
import tiktoken
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    message_chunk_to_message,
)
from langchain_core.runnables import Runnable, RunnableConfig

logger = structlog.get_logger(__name__)

MessagesStream = AsyncIterator[Union[list[AnyMessage], str, dict]]


def _extract_usage(event_data: dict) -> Optional[dict]:
    output = event_data.get("output")
    if isinstance(output, dict):
        llm_output = output.get("llm_output") or {}
        token_usage = llm_output.get("token_usage") or llm_output.get("usage")
        if token_usage:
            return token_usage
    if hasattr(output, "response_metadata"):
        token_usage = getattr(output, "response_metadata", {}).get("token_usage")
        if token_usage:
            return token_usage
    return None


def _message_to_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return orjson.dumps(content).decode()


def _estimate_usage(messages: dict[str, BaseMessage]) -> Optional[dict]:
    ai_messages = [msg for msg in messages.values() if isinstance(msg, AIMessage)]
    if not ai_messages:
        return None
    last_ai = ai_messages[-1]
    prompt_text = "\n".join(
        _message_to_text(msg)
        for msg in messages.values()
        if msg is not last_ai
    )
    completion_text = _message_to_text(last_ai)
    try:
        encoder = tiktoken.encoding_for_model("gpt-4o")
    except Exception:
        encoder = tiktoken.get_encoding("cl100k_base")
    prompt_tokens = len(encoder.encode(prompt_text)) if prompt_text else 0
    completion_tokens = len(encoder.encode(completion_text)) if completion_text else 0
    total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated": True,
    }


async def astream_state(
    app: Runnable,
    input: Union[Sequence[AnyMessage], Dict[str, Any]],
    config: RunnableConfig,
) -> MessagesStream:
    """Stream messages from the runnable."""
    root_run_id: Optional[str] = None
    messages: dict[str, BaseMessage] = {}

    async for event in app.astream_events(
        input, config, version="v1", stream_mode="values", exclude_tags=["nostream"]
    ):
        if event["event"] == "on_chain_start" and not root_run_id:
            root_run_id = event["run_id"]
            yield root_run_id
        elif event["event"] == "on_chain_stream" and event["run_id"] == root_run_id:
            new_messages: list[BaseMessage] = []

            # event["data"]["chunk"] is a Sequence[AnyMessage] or a Dict[str, Any]
            state_chunk_msgs: Union[Sequence[AnyMessage], Dict[str, Any]] = event[
                "data"
            ]["chunk"]
            if isinstance(state_chunk_msgs, dict):
                state_chunk_msgs = event["data"]["chunk"]["messages"]

            for msg in state_chunk_msgs:
                msg_id = msg["id"] if isinstance(msg, dict) else msg.id
                if msg_id in messages and msg == messages[msg_id]:
                    continue
                else:
                    messages[msg_id] = msg
                    new_messages.append(msg)
            if new_messages:
                yield new_messages
        elif event["event"] == "on_chat_model_stream":
            message: BaseMessage = event["data"]["chunk"]
            if message.id not in messages:
                messages[message.id] = message
            else:
                messages[message.id] += message
            yield [messages[message.id]]
        elif event["event"] in ("on_chat_model_end", "on_llm_end"):
            usage = _extract_usage(event["data"])
            if not usage:
                usage = _estimate_usage(messages)
            if usage:
                yield {"event": "usage", "data": usage}


def _default(obj) -> Any:
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


dumps = functools.partial(orjson.dumps, default=_default)


async def to_sse(messages_stream: MessagesStream) -> AsyncIterator[dict]:
    """Consume the stream into an EventSourceResponse"""
    try:
        async for chunk in messages_stream:
            # EventSourceResponse expects a string for data
            # so after serializing into bytes, we decode into utf-8
            # to get a string.
            if isinstance(chunk, dict) and "event" in chunk and "data" in chunk:
                yield {
                    "event": chunk["event"],
                    "data": orjson.dumps(chunk["data"]).decode(),
                }
            elif isinstance(chunk, str):
                yield {
                    "event": "metadata",
                    "data": orjson.dumps({"run_id": chunk}).decode(),
                }
            else:
                yield {
                    "event": "data",
                    "data": dumps(
                        [message_chunk_to_message(msg) for msg in chunk]
                    ).decode(),
                }
    except Exception:
        logger.warn("error in stream", exc_info=True)
        yield {
            "event": "error",
            # Do not expose the error message to the client since
            # the message may contain sensitive information.
            # We'll add client side errors for validation as well.
            "data": orjson.dumps(
                {"status_code": 500, "message": "Internal Server Error"}
            ).decode(),
        }

    # Send an end event to signal the end of the stream
    yield {"event": "end"}
