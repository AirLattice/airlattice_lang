import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layout } from "../components/Layout";
import { ChatList } from "../components/ChatList";
import { useChatList } from "../hooks/useChatList";
import { useConfigList } from "../hooks/useConfigList";
import { useMemory } from "../hooks/useMemory";
import { cn } from "../utils/cn";

function formatTimestamp(value: string | null) {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function MemoryPage() {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { chats, deleteChat } = useChatList();
  const { configs } = useConfigList();
  const { items, loading, error, remove, clear } = useMemory();

  const selectChat = useCallback(
    async (id: string | null) => {
      if (!id) {
        const firstAssistant = configs?.[0]?.assistant_id ?? null;
        navigate(firstAssistant ? `/assistant/${firstAssistant}` : "/");
        window.scrollTo({ top: 0 });
      } else {
        navigate(`/thread/${id}`);
      }
    },
    [configs, navigate],
  );

  const selectConfig = useCallback(
    (id: string | null) => {
      navigate(id ? `/assistant/${id}` : "/");
    },
    [navigate],
  );

  return (
    <Layout
      subtitle={<span className="inline-flex gap-1 items-center">Memory</span>}
      sidebarOpen={sidebarOpen}
      setSidebarOpen={setSidebarOpen}
      sidebar={
        <ChatList
          chats={chats}
          configs={configs}
          enterChat={selectChat}
          deleteChat={deleteChat}
          enterConfig={selectConfig}
          enterMemory={() => navigate("/memory")}
        />
      }
    >
      <div className="mx-auto w-full max-w-4xl px-4 pb-10">
        <div className="flex flex-col gap-2 mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">
            Personal memory
          </h1>
          <p className="text-sm text-gray-500">
            This list stores everything you have said. It is used to answer
            future questions across all chats.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={async () => {
                if (
                  items?.length &&
                  window.confirm("Clear all stored memories?")
                ) {
                  await clear();
                }
              }}
              className={cn(
                "inline-flex items-center rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50",
                !items?.length && "opacity-50 cursor-not-allowed",
              )}
              disabled={!items?.length}
            >
              Clear all
            </button>
          </div>
        </div>

        {loading && (
          <div className="text-sm text-gray-500 animate-pulse">Loading...</div>
        )}
        {!loading && error && (
          <div className="text-sm text-red-600">{error}</div>
        )}
        {!loading && !error && (items?.length ?? 0) === 0 && (
          <div className="text-sm text-gray-500">
            No memories stored yet.
          </div>
        )}

        <div className="flex flex-col gap-4">
          {items?.map((item) => (
            <div
              key={item.id}
              className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>
                  {item.role ? item.role.toUpperCase() : "MEMORY"} ·{" "}
                  {formatTimestamp(item.created_at)}
                </span>
                <button
                  type="button"
                  onClick={async () => {
                    if (window.confirm("Delete this memory?")) {
                      await remove(item.id);
                    }
                  }}
                  className="text-gray-500 hover:text-red-600"
                >
                  Delete
                </button>
              </div>
              <div className="mt-2 text-sm text-gray-900 whitespace-pre-wrap">
                {item.content}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
