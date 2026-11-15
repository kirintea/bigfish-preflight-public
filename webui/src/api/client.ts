// HTTP client for the local API and management endpoints.
// Credentials stay in memory and are attached only to management endpoints.
let credential = "";
export const setCredential = (value: string) => {
  credential = value.trim();
};
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public requestId: string,
  ) {
    super(detail);
  }
}
export async function request<T = any>(
  path: string,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController();
  const { timeoutMs = 120000, ...fetchOptions } = options;
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : undefined;
  try {
    const response = await fetch(path, {
      ...fetchOptions,
      signal: options.signal || controller.signal,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(path.startsWith("/api/test/") || path.startsWith("/api/v1/observe/")
          ? { Authorization: `Bearer ${credential}` }
          : {}),
        ...options.headers,
      },
    });
    const data = await response.json();
    if (!response.ok)
      throw new ApiError(
        response.status,
        data.reason || data.detail || "request_failed",
        response.headers.get("x-request-id") || "",
      );
    return data;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('请求等待超时，请重试；已确认的消息不会重复发送。');
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function streamPost(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const response = await fetch(path, {
    method: "POST",
    signal,
    body: JSON.stringify(body),
    headers: {
      "Content-Type": "application/json",
      ...(path.startsWith("/api/test/") || path.startsWith("/api/v1/observe/")
        ? { Authorization: `Bearer ${credential}` }
        : {}),
      Accept: "text/event-stream",
    },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      data.reason || data.detail || "request_failed",
      response.headers.get("x-request-id") || "",
    );
  }
  return response;
}
export const client = {
  get: <T = any>(path: string) => request<T>(path),
  post: <T = any>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
};
export const id = () => crypto.randomUUID().replaceAll("-", "");
export const command = (state: { run_epoch: string; revision: number }) => ({
  command_id: id(),
  run_epoch: state.run_epoch,
  expected_revision: state.revision,
});
