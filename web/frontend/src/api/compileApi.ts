import type { AnalyzeResult, Example, RunResult } from "../types/ast";

// Relative URLs: Vite forwards /api to the backend during development
// (vite.config.ts), and the built frontend is served by the backend itself.
const BACKEND_URL = "";

export class CompileError extends Error {}

interface AnalyzeResponseBody {
  parse_tree: AnalyzeResult["parseTree"];
  ast: AnalyzeResult["ast"];
  error: AnalyzeResult["error"];
}

interface ExampleResponseBody {
  name: string;
  source: string;
}

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new CompileError("Не вдалося з'єднатися з backend");
  }
  if (!response.ok) {
    throw new CompileError(`Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function analyzeSource(sourceCode: string, signal?: AbortSignal): Promise<AnalyzeResult> {
  const body = await request<AnalyzeResponseBody>("/api/analyze", { source: sourceCode }, signal);
  return { parseTree: body.parse_tree, ast: body.ast, error: body.error };
}

export async function runSource(
  sourceCode: string,
  initialState: Record<string, string>,
  maxSteps: number,
  signal?: AbortSignal,
): Promise<RunResult> {
  // Values are sent as strings so that big integers keep every digit.
  return request<RunResult>(
    "/api/run",
    { source: sourceCode, initial_state: initialState, max_steps: maxSteps },
    signal,
  );
}

export async function fetchExamples(): Promise<Example[]> {
  const body = await request<ExampleResponseBody[]>("/api/examples");
  return body.map((example) => ({ name: example.name, sourceCode: example.source }));
}