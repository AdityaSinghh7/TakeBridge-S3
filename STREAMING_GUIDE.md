# TakeBridge Orchestrator Streaming Guide

This document walks through, in exhaustive detail, how to connect a client to the `/orchestrate/stream` endpoint, consume the Server-Sent Events (SSE) the orchestrator emits, and surface them inside a Next.js application. The guide is divided into five progressively deeper sections so you can adopt the entire workflow or cherry-pick the pieces you need.

> **Prerequisites**
>
> - FastAPI server from this repo is running and reachable (default `http://localhost:8000`).
> - You have a task payload ready to send (at minimum `{ "task": "…" }`).
> - Node.js ≥ 18 (required for the built-in `fetch` streaming APIs used by Next.js).
>
> All snippets use TypeScript/ES modules syntax and assume the Next.js 13+ App Router.

---

## 1. Sending a Request to `/orchestrate/stream`

The `/orchestrate/stream` endpoint accepts the same payload as `/orchestrate`, but it replies as an SSE stream. You must keep the HTTP connection open until the orchestrator finishes.

### 1.1 Minimal Request Payload

```jsonc
{
  "task": "Open the calendar app and list today’s meetings"
}
```

- `task` *(string, required)* – natural language instruction sent to the worker.
- Optional nested overrides (`worker`, `grounding`, `controller`, `platform`, `enable_code_execution`) follow the shapes in `computer_use_agent/orchestrator/data_types.py`.

### 1.2 Making the Request (Node.js / server-side fetch)

```ts
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL ?? "http://localhost:8000";

async function openStream(task: string): Promise<Response> {
  const res = await fetch(`${ORCHESTRATOR_URL}/orchestrate/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ task }),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Failed to open stream: ${res.status} ${res.statusText}`);
  }

  return res;
}
```

Key callouts:
- Always set `Accept: text/event-stream` so FastAPI keeps the response streaming.
- Check that `res.body` exists; it’s a `ReadableStream` carrying the SSE data.
- The connection stays open until you read an `event: response.completed` or `event: response.failed` message (or the server closes the socket on error).

---

## 2. Subscribing to the Streaming Event Emitters

The orchestrator publishes structured events via a custom emitter stack (`computer_use_agent/utils/streaming.py`). Inside the server each module calls `emit_event(...)`; on the wire everything is serialized as standard SSE lines.

### 2.1 SSE Frame Anatomy

Each payload the server pushes follows the SSE spec:

```
event: <event-name>
data: <json-payload>

```

Blank line terminates a frame. Multiple `data:` lines are concatenated before parsing.

### 2.2 Streaming Flow Overview

1. Client posts to `/orchestrate/stream`.
2. Server immediately emits two lifecycle events:
   - `response.created` → `{ "status": "accepted" }`
   - `response.in_progress` → `{ "status": "running" }`
3. All downstream agents reuse the active emitter context, so you receive real-time notes such as `worker.step.started`, `grounding.generate_coords.completed`, `code_agent.step.execution`, etc.
4. When the runner completes (success/fail/timeout) the server emits:
   - `response` → full JSON `RunnerResult` snapshot.
   - `response.completed` → `{ "status": "success", "completion_reason": "DONE" }` (values vary).

The connection ends naturally right after `response.completed` (or `response.failed`).

---

## 3. Parsing Server-Emitted Events

### 3.1 Canonical Event List

Below is the full taxonomy of events currently emitted by the computer-use agent stack. Event names are sanitized to `[A-Za-z0-9-_.]`, so dots in cost sources are preserved. Payloads are JSON objects.

| Event name | When it fires | Representative payload |
| --- | --- | --- |
| `response.created` | Immediately after the POST is accepted | `{ "status": "accepted" }` |
| `response.in_progress` | Right before orchestration kicks off | `{ "status": "running" }` |
| `response.failed` | Runner raised an exception | `{ "error": "..." }` |
| `response` | Final `RunnerResult` dataclass | Mirrors `RunnerResult` structure |
| `response.completed` | Final status (success/failed/timeout) | `{ "status": "success", "completion_reason": "DONE" }` |
| `runner.started` | Runner initialises agents | `{ "task": "...", "max_steps": 8, "platform": "linux" }` |
| `runner.step.started` | Each orchestrator loop iteration | `{ "step": 1 }` |
| `runner.step.completed` | After behavior narrator and action handling | `{ "step": 1, "status": "in_progress", "action": "..." }` |
| `runner.completed` | After loop terminates | `{ "status": "success", "completion_reason": "DONE", "steps": 3 }` |
| `worker.step.started` | Worker begins generating plan for step | `{ "step": 1 }` |
| `worker.reflection.completed` | Reflection agent finished | `{ "step": 1, "reflection": "...", "thoughts": "..." }` |
| `worker.step.ready` | Worker prepared exec code | `{ "step": 1, "plan": "...", "exec_code": "..." }` |
| `behavior_narrator.completed` | Behavior narrator judgement returned | `{ "step": 1, "action": "...", "caption": "Fact..." }` |
| `grounding.generate_coords.started` | Coordinate lookup begins | `{ "ref_expr": "Click the OK button" }` |
| `grounding.generate_coords.service_fallback` | External grounding service failed | `{ "ref_expr": "..." }` |
| `grounding.generate_coords.completed` | Coordinates resolved | `{ "ref_expr": "...", "coords": [1024, 640], "source": "service" }` |
| `grounding.generate_text_coords.started/completed` | OCR span grounding | `{ "phrase": "Submit", "alignment": "start" }` / plus `coords` |
| `grounding.code_agent.started/completed/skipped` | Worker delegated to code agent | Payload includes `task`, `summary`, `steps_executed` |
| `code_agent.session.started` | Multi-step code assistant engaged | `{ "task": "...", "budget": 20 }` |
| `code_agent.step.response` | Code agent produced new response | `{ "step": 1, "action": "...", "thoughts": "..." }` |
| `code_agent.step.execution` | VM executed generated code | `{ "step": 1, "code_type": "python", "status": "success", "output": "..." }` |
| `code_agent.step.completed` | Step state after execution result appended | `{ "step": 1, "status": "success" }` |
| `code_agent.session.completed` | Code agent run over | `{ "completion_reason": "DONE", "summary": "..." }` |
| `grounding.fallback_coords.*` / other cost-source events | Any `call_llm_safe` invocation with `cost_source` set | `{ "attempts": 1, "model": "o4-mini", "text": "..." }` |

> **Tip:** Any cost source such as `worker.generator` or `behavior_narrator` produces `worker.generator.started` / `worker.generator.completed` telemetry automatically.

### 3.2 Incremental Parsing Logic

You must handle partial chunks because SSE lines can arrive split across TCP frames. A robust parser:

1. Read from the `ReadableStream` as UTF-8 text.
2. Accumulate into a buffer.
3. Split on `\n\n` (double newline) when a full frame is available.
4. For each frame, split into lines, read the last `data:` line, parse JSON.
5. Dispatch by `event` name.

```ts
import { TextDecoderStream } from "stream/web"; // Node 18+

async function* parseSSE(stream: ReadableStream<Uint8Array>) {
  const decoder = new TextDecoderStream();
  const reader = stream.pipeThrough(decoder).getReader();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value ?? "";

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");

        if (!rawEvent) continue;
        const lines = rawEvent.split(/\n/);
        let eventName = "message";
        const dataLines: string[] = [];

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
          }
        }

        const rawData = dataLines.join("\n");
        let parsed: unknown = rawData;
        try {
          parsed = rawData ? JSON.parse(rawData) : null;
        } catch (err) {
          console.error("Failed to parse SSE data", err, rawData);
        }

        yield { event: eventName, data: parsed };
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

---

## 4. Storing Parsed Events for Frontend Consumption

The Next.js server-side code should map raw SSE frames into a typed state object. One strategy is to maintain a mutable store while streaming, then expose it to React components once the run finishes.

### 4.1 Suggested State Shape

```ts
type RunPhase = "idle" | "running" | "success" | "failed" | "timeout";

type WorkerStep = {
  step: number;
  plan?: string;
  execCode?: string;
  reflection?: string;
  reflectionThoughts?: string;
  behaviorCaption?: string;
  behaviorThoughts?: string;
  action?: string;
};

type CodeAgentSnapshot = {
  active: boolean;
  budget?: number;
  stepsExecuted?: number;
  completionReason?: string;
  summary?: string;
  steps: Array<{
    step: number;
    action?: string;
    thoughts?: string;
    status?: string;
    output?: string;
    error?: string;
  }>;
};

type GroundingActivity = {
  refs: Array<{ phrase: string; coords?: [number, number]; source?: string }>;
  codeDelegations: Array<{ task: string; completionReason?: string; summary?: string }>;
};

type OrchestrateRunState = {
  phase: RunPhase;
  statusMessage?: string;
  task: string;
  maxSteps?: number;
  platform?: string | null;
  steps: Map<number, WorkerStep>;
  codeAgent: CodeAgentSnapshot;
  grounding: GroundingActivity;
  rawResult?: unknown; // captures the final RunnerResult
  errors: string[];
};
```

### 4.2 Event Reducer

Create a reducer that takes `{ event, data }` tuples and mutates the state. Example for a few events:

```ts
function applyEvent(state: OrchestrateRunState, { event, data }: { event: string; data: any }) {
  switch (event) {
    case "response.created":
      state.phase = "running";
      state.statusMessage = "Request accepted";
      return;
    case "runner.started":
      state.maxSteps = data?.max_steps ?? data?.maxSteps;
      state.platform = data?.platform ?? null;
      return;
    case "worker.step.ready": {
      const step = data?.step;
      if (!step) return;
      const summary = state.steps.get(step) ?? { step };
      summary.plan = data?.plan;
      summary.execCode = data?.exec_code ?? data?.execCode;
      summary.reflection = data?.reflection;
      summary.reflectionThoughts = data?.reflection_thoughts ?? data?.reflectionThoughts;
      state.steps.set(step, summary);
      return;
    }
    case "behavior_narrator.completed": {
      const step = data?.step;
      if (!step) return;
      const summary = state.steps.get(step) ?? { step };
      summary.behaviorCaption = data?.caption;
      summary.behaviorThoughts = data?.thoughts;
      summary.action = data?.action;
      state.steps.set(step, summary);
      return;
    }
    case "code_agent.step.execution": {
      const stepEntry = {
        step: data?.step,
        status: data?.status,
        output: data?.output,
        error: data?.error,
      };
      state.codeAgent.steps.push(stepEntry);
      return;
    }
    case "response.completed":
      state.phase = (data?.status ?? "success") as RunPhase;
      state.statusMessage = data?.completion_reason ?? data?.completionReason;
      return;
    case "response.failed":
      state.phase = "failed";
      state.errors.push(String(data?.error ?? "Unknown error"));
      return;
    case "response":
      state.rawResult = data;
      return;
    default:
      if (event.endsWith(".failed")) {
        state.errors.push(JSON.stringify({ event, data }));
      }
  }
}
```

Maintain the map so later components can render step-by-step cards without re-parsing raw JSON.

---

## 5. Integrating with Next.js (Server-Side Component Strategy)

We’ll build a dedicated route module that performs the backend work (call + parse + store) and exposes the result to React components. The approach consists of three layers:

1. **Server Utility** – encapsulates the fetching/parsing pipeline.
2. **API Route (optional)** – if you want to expose the processed timeline to browsers via JSON.
3. **Server Component** – invokes the utility during `async` render and passes structured data to a client component for live UI.

### 5.1 Server Utility (`lib/orchestrateStream.ts`)

```ts
import { cache } from "react"; // optional memoisation

export const orchestrateStream = cache(async function orchestrateStream(task: string) {
  const response = await openStream(task); // reuse function from Section 1.2
  const state: OrchestrateRunState = {
    phase: "running",
    task,
    steps: new Map(),
    codeAgent: { active: false, steps: [] },
    grounding: { refs: [], codeDelegations: [] },
    errors: [],
  };

  for await (const frame of parseSSE(response.body!)) {
    applyEvent(state, frame);

    if (frame.event === "code_agent.session.started") {
      state.codeAgent.active = true;
      state.codeAgent.budget = frame.data?.budget;
    }

    if (frame.event === "grounding.code_agent.completed") {
      state.codeAgent.stepsExecuted = frame.data?.steps_executed;
      state.codeAgent.summary = frame.data?.summary;
      state.codeAgent.completionReason = frame.data?.completion_reason;
    }

    if (frame.event === "grounding.generate_coords.completed") {
      state.grounding.refs.push({
        phrase: frame.data?.ref_expr,
        coords: frame.data?.coords,
        source: frame.data?.source,
      });
    }
    // Continue mapping events as needed…
  }

  return {
    ...state,
    steps: Array.from(state.steps.values()).sort((a, b) => a.step - b.step),
  };
});
```

### 5.2 Server Route Handler (`app/api/orchestrate/route.ts`)

Expose a JSON API for the frontend or integration tests. This route simply calls the server utility and returns the final state once streaming ends.

```ts
import { NextResponse } from "next/server";
import { orchestrateStream } from "@/lib/orchestrateStream";

export async function POST(request: Request) {
  const { task } = await request.json();
  if (!task) {
    return NextResponse.json({ error: "task is required" }, { status: 400 });
  }

  try {
    const result = await orchestrateStream(task);
    return NextResponse.json(result, { status: 200 });
  } catch (error) {
    console.error(error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
```

### 5.3 Server Component (`app/run/page.tsx`)

Render the orchestrator output directly from a server component. You can pair it with a client component if you want interactivity.

```tsx
import ResultTimeline from "@/components/ResultTimeline"; // client component
import { orchestrateStream } from "@/lib/orchestrateStream";

export default async function RunPage({ searchParams }: { searchParams: { task?: string } }) {
  const task = searchParams.task ?? "Open calculator and add 42 + 58";
  const runState = await orchestrateStream(task);

  return (
    <main className="prose mx-auto p-6">
      <h1>Agent Run</h1>
      <p><strong>Task:</strong> {runState.task}</p>
      <p><strong>Status:</strong> {runState.phase}</p>
      {runState.statusMessage && <p><strong>Reason:</strong> {runState.statusMessage}</p>}
      {runState.errors.length > 0 && (
        <details className="bg-red-50 border border-red-200 rounded p-3">
          <summary>Errors ({runState.errors.length})</summary>
          <pre className="whitespace-pre-wrap text-sm">{runState.errors.join("\n")}</pre>
        </details>
      )}
      <ResultTimeline runState={runState} />
    </main>
  );
}
```

### 5.4 Client Component to Display the Timeline (`components/ResultTimeline.tsx`)

```tsx
"use client";
import type { OrchestrateRunState } from "@/lib/types";

export default function ResultTimeline({ runState }: { runState: OrchestrateRunState }) {
  return (
    <section className="space-y-4">
      {runState.steps.map((step) => (
        <article key={step.step} className="rounded border border-gray-200 p-4">
          <header className="flex justify-between">
            <span className="font-bold">Step {step.step}</span>
            {step.action && <span className="text-sm text-gray-500">Action: {step.action}</span>}
          </header>
          {step.plan && (
            <details className="mt-2">
              <summary className="cursor-pointer font-semibold">Plan</summary>
              <pre className="whitespace-pre-wrap text-sm bg-slate-50 p-2 rounded">{step.plan}</pre>
            </details>
          )}
          {step.execCode && (
            <details className="mt-2">
              <summary className="cursor-pointer font-semibold">Executable Code</summary>
              <pre className="whitespace-pre-wrap text-sm bg-slate-50 p-2 rounded">{step.execCode}</pre>
            </details>
          )}
          {step.reflection && (
            <p className="mt-2 text-sm"><strong>Reflection:</strong> {step.reflection}</p>
          )}
          {step.behaviorCaption && (
            <p className="mt-2 text-sm"><strong>Behavior:</strong> {step.behaviorCaption}</p>
          )}
        </article>
      ))}
    </section>
  );
}
```

### 5.5 Error Handling and Abort Logic

- Wrap `openStream` in `AbortController` to support cancellation when a user navigates away.
- Consider timeouts: if no `response.completed` arrives within a threshold, abort the request and surface an error state.
- The reducer in §4 should log any `*.failed` or unexpected events so you can monitor edge cases.

### 5.6 Scaling Considerations

- **Long-running runs:** For very long workflows, persist intermediate events (Redis, database, or streamed into a client via Next.js `server-sent events` in your own API route).
- **Multiple observers:** If several clients need the same run, convert the streaming utility into a background worker that fans out updates over WebSockets.
- **Partial rendering:** The server component example waits for full completion. For real-time UX, expose an API route that relays events as they happen, then let a client component subscribe with `EventSource`.

---

## Appendix: Testing Checklist

1. Start the orchestrator server (`uvicorn server.api.server:app --reload`).
2. Run `curl -N http://localhost:8000/orchestrate/stream -H 'Content-Type: application/json' -d '{ "task": "Ping" }'` to confirm raw SSE output.
3. Execute `npm run dev` in the Next.js app and navigate to `/run?task=Open%20Calculator`. Confirm the timeline renders after the run completes.
4. Trigger a failure (e.g., unplug the controller) to confirm `response.failed` surfaces in `runState.errors`.
5. Validate Grounding + Code Agent flows by sending a task that requires both; confirm the corresponding sections populate in the UI.

With these steps in place, your Next.js application can deliver a detailed, per-agent breakdown of the orchestrator’s reasoning, actions, and reflections—fully synchronised with the backend SSE stream.
