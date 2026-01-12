import { useCallback, useEffect, useState } from "react";
import { MemoryItem } from "../types";
import { clearMemory, deleteMemory, listMemory } from "../api/memory";

export function useMemory() {
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMemory();
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memory.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const remove = useCallback(
    async (id: string) => {
      const deleted = await deleteMemory(id);
      if (deleted) {
        setItems((current) => (current || []).filter((item) => item.id !== id));
      }
      return deleted;
    },
    [setItems],
  );

  const clear = useCallback(async () => {
    const deleted = await clearMemory();
    if (deleted > 0) {
      setItems([]);
    }
    return deleted;
  }, []);

  return {
    items,
    loading,
    error,
    refresh,
    remove,
    clear,
  };
}
