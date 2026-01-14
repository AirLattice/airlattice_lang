import { authFetch } from "./authFetch";

type IngestStatus = {
  job_id: string;
  status: "running" | "done" | "error" | "canceled";
  progress: number;
  error?: string | null;
};

export async function startIngest(
  formData: FormData,
  onProgress?: (progress: number) => void,
  signal?: AbortSignal,
  onJobId?: (jobId: string) => void,
) {
  const response = await authFetch("/ingest", {
    method: "POST",
    body: formData,
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to start ingest.");
  }
  const data = (await response.json()) as { job_id?: string };
  if (!data.job_id) {
    return;
  }
  onJobId?.(data.job_id);
  await waitForIngest(data.job_id, onProgress, signal);
}

export async function cancelIngest(jobId: string) {
  const response = await authFetch(`/ingest/${jobId}/cancel`, {
    method: "POST",
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to cancel ingest.");
  }
}

async function waitForIngest(
  jobId: string,
  onProgress?: (progress: number) => void,
  signal?: AbortSignal,
) {
  // Poll until the ingestion finishes.
  for (;;) {
    if (signal?.aborted) {
      throw new DOMException("Ingest canceled", "AbortError");
    }
    const response = await authFetch(`/ingest/${jobId}`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "Failed to check ingest status.");
    }
    const status = (await response.json()) as IngestStatus;
    if (typeof status.progress === "number") {
      onProgress?.(status.progress);
    }
    if (status.status === "canceled") {
      throw new DOMException("Ingest canceled", "AbortError");
    }
    if (status.status === "done") {
      return;
    }
    if (status.status === "error") {
      throw new Error(status.error || "Ingest failed.");
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
