import { useCallback, useState } from "react";
import { InformationCircleIcon } from "@heroicons/react/24/outline";
import { Chat } from "./components/Chat";
import { ChatList } from "./components/ChatList";
import { Layout } from "./components/Layout";
import { NewChat } from "./components/NewChat";
import { useChatList } from "./hooks/useChatList";
import { useSchemas } from "./hooks/useSchemas";
import { useStreamState } from "./hooks/useStreamState";
import {
  useConfigList,
  Config as ConfigInterface,
} from "./hooks/useConfigList";
import { Config } from "./components/Config";
import { MessageWithFiles } from "./utils/formTypes.ts";
import { useNavigate } from "react-router-dom";
import { useThreadAndAssistant } from "./hooks/useThreadAndAssistant.ts";
import { Message } from "./types.ts";
import { OrphanChat } from "./components/OrphanChat.tsx";
import { cancelIngest, startIngest } from "./utils/ingest.ts";

function App(props: { edit?: boolean }) {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [ingestProgress, setIngestProgress] = useState<number | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [ingestController, setIngestController] =
    useState<AbortController | null>(null);
  const [ingestJobId, setIngestJobId] = useState<string | null>(null);
  const { chats, createChat, updateChat, deleteChat } = useChatList();
  const { configs, saveConfig, deleteConfig } = useConfigList();
  const { startStream, stopStream, stream } = useStreamState();
  const { configSchema, configDefaults } = useSchemas();

  const { currentChat, assistantConfig, isLoading } = useThreadAndAssistant();

  const startTurn = useCallback(
    async (
      message: MessageWithFiles | null,
      thread_id: string,
      assistantType: string,
      config?: Record<string, unknown>,
    ) => {
      const files = message?.files || [];
      if (files.length > 0) {
        setIngestProgress(0);
        setIngestError(null);
        const controller = new AbortController();
        setIngestController(controller);
        setIngestJobId(null);
        try {
          const formData = files.reduce((formData, file) => {
            formData.append("files", file);
            return formData;
          }, new FormData());
          formData.append(
            "config",
            JSON.stringify({ configurable: { thread_id } }),
          );
          await startIngest(
            formData,
            (progress) => {
              const percent = Math.round(progress * 1000) / 10;
              setIngestProgress(Math.min(99.9, percent));
            },
            controller.signal,
            (jobId) => setIngestJobId(jobId),
          );
        } catch (error) {
          if (error instanceof DOMException && error.name === "AbortError") {
            setIngestError("Upload canceled.");
            return;
          }
          setIngestError(
            error instanceof Error ? error.message : "Ingest failed.",
          );
          return;
        } finally {
          setIngestProgress(null);
          setIngestController(null);
          setIngestJobId(null);
        }
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let input: Message[] | Record<string, any> | null = null;

      if (message) {
        // Set the input to an array of messages. This is the default input
        // format for all assistant types.
        input = [
          {
            content: message.message,
            additional_kwargs: {},
            type: "human",
            example: false,
            id: `human-${Math.random()}`,
          },
        ];

        if (assistantType === "chat_retrieval") {
          // The RAG assistant type requires an object with a `messages` field.
          input = {
            messages: input,
          };
        }
      }

      await startStream(input, thread_id, config);
    },
    [startStream],
  );

  const startChat = useCallback(
    async (config: ConfigInterface, message: MessageWithFiles) => {
      const chat = await createChat(message.message, config.assistant_id);
      navigate(`/thread/${chat.thread_id}`);
      const assistantType = config.config.configurable?.type as string;
      return startTurn(message, chat.thread_id, assistantType);
    },
    [createChat, navigate, startTurn],
  );

  const selectChat = useCallback(
    async (id: string | null) => {
      if (currentChat) {
        stopStream?.(true);
      }
      if (!id) {
        const firstAssistant = configs?.[0]?.assistant_id ?? null;
        navigate(firstAssistant ? `/assistant/${firstAssistant}` : "/");
        window.scrollTo({ top: 0 });
      } else {
        navigate(`/thread/${id}`);
      }
      if (sidebarOpen) {
        setSidebarOpen(false);
      }
    },
    [currentChat, sidebarOpen, stopStream, configs, navigate],
  );

  const selectConfig = useCallback(
    (id: string | null) => {
      navigate(id ? `/assistant/${id}` : "/");
    },
    [navigate],
  );

  return (
    <Layout
      subtitle={
        assistantConfig ? (
          <span className="inline-flex gap-1 items-center">
            {assistantConfig.name}
            <InformationCircleIcon
              className="h-5 w-5 cursor-pointer text-indigo-600"
              onClick={() => {
                selectConfig(assistantConfig.assistant_id);
              }}
            />
          </span>
        ) : null
      }
      sidebarOpen={sidebarOpen}
      setSidebarOpen={setSidebarOpen}
      sidebar={
        <ChatList
          chats={chats}
          configs={configs}
          enterChat={selectChat}
          deleteChat={deleteChat}
          enterConfig={selectConfig}
        />
      }
    >
      {currentChat && assistantConfig && (
        <Chat
          startStream={startTurn}
          stopStream={stopStream}
          stream={stream}
          ingestProgress={ingestProgress}
          ingestError={ingestError}
          onCancelIngest={async () => {
            if (ingestJobId) {
              try {
                await cancelIngest(ingestJobId);
              } catch (error) {
                setIngestError(
                  error instanceof Error
                    ? error.message
                    : "Failed to cancel ingest.",
                );
              }
            }
            ingestController?.abort();
          }}
        />
      )}
      {currentChat && !assistantConfig && (
        <OrphanChat chat={currentChat} updateChat={updateChat} />
      )}
      {!currentChat && assistantConfig && !props.edit && (
        <NewChat
          startChat={startChat}
          configSchema={configSchema}
          configDefaults={configDefaults}
          configs={configs}
          saveConfig={saveConfig}
          enterConfig={selectConfig}
          deleteConfig={deleteConfig}
        />
      )}
      {!currentChat && assistantConfig && props.edit && (
        <Config
          className="mb-6"
          config={assistantConfig}
          configSchema={configSchema}
          configDefaults={configDefaults}
          saveConfig={saveConfig}
          enterConfig={selectConfig}
          edit={props.edit}
        />
      )}
      {!currentChat && !assistantConfig && !isLoading && (
        <Config
          className="mb-6"
          config={null}
          configSchema={configSchema}
          configDefaults={configDefaults}
          saveConfig={saveConfig}
          enterConfig={selectConfig}
        />
      )}
      {isLoading && <div>Loading...</div>}
    </Layout>
  );
}

export default App;
