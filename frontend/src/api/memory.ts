import { MemoryItem } from "../types";
import { authFetch } from "../utils/authFetch";

export async function listMemory(
  limit = 200,
  offset = 0,
): Promise<MemoryItem[]> {
  const response = await authFetch(`/memory?limit=${limit}&offset=${offset}`, {
    headers: {
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error("Failed to load memory.");
  }
  return (await response.json()) as MemoryItem[];
}

export async function deleteMemory(id: string): Promise<boolean> {
  const response = await authFetch(`/memory/${id}`, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error("Failed to delete memory.");
  }
  const data = (await response.json()) as { deleted?: boolean };
  return Boolean(data.deleted);
}

export async function clearMemory(): Promise<number> {
  const response = await authFetch("/memory", {
    method: "DELETE",
    headers: {
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error("Failed to clear memory.");
  }
  const data = (await response.json()) as { deleted?: number };
  return data.deleted ?? 0;
}
