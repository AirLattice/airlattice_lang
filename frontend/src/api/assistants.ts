import { Config } from "../hooks/useConfigList";
import { authFetch } from "../utils/authFetch";

export async function getAssistant(
  assistantId: string,
): Promise<Config | null> {
  try {
    const response = await authFetch(`/assistants/${assistantId}`);
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Config;
  } catch (error) {
    console.error("Failed to fetch assistant:", error);
    return null;
  }
}

export async function getAssistants(): Promise<Config[] | null> {
  try {
    const response = await authFetch(`/assistants/`);
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Config[];
  } catch (error) {
    console.error("Failed to fetch assistants:", error);
    return null;
  }
}
