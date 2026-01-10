import { Chat } from "../types";
import { authFetch } from "../utils/authFetch";

export async function getThread(threadId: string): Promise<Chat | null> {
  try {
    const response = await authFetch(`/threads/${threadId}`);
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Chat;
  } catch (error) {
    console.error("Failed to fetch assistant:", error);
    return null;
  }
}
