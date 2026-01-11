/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { Message, TokenUsage } from "../types";
import { getAuthToken } from "../utils/auth";

export interface StreamState {
  status: "inflight" | "error" | "done";
  messages?: Message[] | Record<string, any>;
  run_id?: string;
  usage?: TokenUsage | null;
}

export interface StreamStateProps {
  stream: StreamState | null;
  startStream: (
    input: Message[] | Record<string, any> | null,
    thread_id: string,
    config?: Record<string, unknown>,
  ) => Promise<void>;
  stopStream?: (clear?: boolean) => void;
}

export function useStreamState(): StreamStateProps {
  const [current, setCurrent] = useState<StreamState | null>(null);
  const [controller, setController] = useState<AbortController | null>(null);

  const extractUsage = (msgs: Message[] | Record<string, any> | null | undefined) => {
    const list = Array.isArray(msgs) ? msgs : msgs?.messages;
    if (!Array.isArray(list)) return null;
    for (let i = list.length - 1; i >= 0; i -= 1) {
      const usage = list[i]?.usage_metadata;
      if (usage?.total_tokens) {
        return {
          prompt_tokens: usage.input_tokens,
          completion_tokens: usage.output_tokens,
          total_tokens: usage.total_tokens,
        } as TokenUsage;
      }
    }
    return null;
  };

  const startStream = useCallback(
    async (
      input: Message[] | Record<string, any> | null,
      thread_id: string,
      config?: Record<string, unknown>,
    ) => {
      const controller = new AbortController();
      setController(controller);
      setCurrent({
        status: "inflight",
        messages: input || [],
        usage: null,
      });

      const token = getAuthToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      await fetchEventSource("/runs/stream", {
        signal: controller.signal,
        method: "POST",
        headers,
        body: JSON.stringify({ input, thread_id, config }),
        openWhenHidden: true,
        onmessage(msg) {
          if (msg.event === "data") {
            const messages = JSON.parse(msg.data);
            const inferredUsage = extractUsage(messages);
            setCurrent((current) => ({
              status: "inflight" as StreamState["status"],
              messages: mergeMessagesById(current?.messages, messages),
              run_id: current?.run_id,
              usage: current?.usage ?? inferredUsage,
            }));
          } else if (msg.event === "metadata") {
            const { run_id } = JSON.parse(msg.data);
            setCurrent((current) => ({
              status: "inflight",
              messages: current?.messages,
              run_id: run_id,
              usage: current?.usage,
            }));
          } else if (msg.event === "usage") {
            const usage = JSON.parse(msg.data);
            setCurrent((current) => ({
              status: current?.status ?? "inflight",
              messages: current?.messages,
              run_id: current?.run_id,
              usage,
            }));
          } else if (msg.event === "error") {
            setCurrent((current) => ({
              status: "error",
              messages: current?.messages,
              run_id: current?.run_id,
              usage: current?.usage,
            }));
          }
        },
        onclose() {
          setCurrent((current) => ({
            status: current?.status === "error" ? current.status : "done",
            messages: current?.messages,
            run_id: current?.run_id,
            usage: current?.usage,
          }));
          setController(null);
        },
        onerror(error) {
          setCurrent((current) => ({
            status: "error",
            messages: current?.messages,
            run_id: current?.run_id,
            usage: current?.usage,
          }));
          setController(null);
          throw error;
        },
      });
    },
    [],
  );

  const stopStream = useCallback(
    (clear: boolean = false) => {
      controller?.abort();
      setController(null);
      if (clear) {
        setCurrent((current) => ({
          status: "done",
          run_id: current?.run_id,
          usage: current?.usage,
        }));
      } else {
        setCurrent((current) => ({
          status: "done",
          messages: current?.messages,
          run_id: current?.run_id,
          usage: current?.usage,
        }));
      }
    },
    [controller],
  );

  return {
    startStream,
    stopStream,
    stream: current,
  };
}

export function mergeMessagesById(
  left: Message[] | Record<string, any> | null | undefined,
  right: Message[] | Record<string, any> | null | undefined,
): Message[] {
  const leftMsgs = Array.isArray(left) ? left : left?.messages;
  const rightMsgs = Array.isArray(right) ? right : right?.messages;

  const merged = (leftMsgs ?? [])?.slice();
  for (const msg of rightMsgs ?? []) {
    const foundIdx = merged.findIndex((m: any) => m.id === msg.id);
    if (foundIdx === -1) {
      merged.push(msg);
    } else {
      merged[foundIdx] = msg;
    }
  }
  return merged;
}
