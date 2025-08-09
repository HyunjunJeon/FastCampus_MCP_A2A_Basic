# Step 3 — Architecture

관련 Step: [../../steps/step3.md](../../steps/step3.md)

```mermaid
graph LR
    subgraph MCP-only
      S1[Supervisor (Graph)]
      P1[Planner ReAct Agent]
      R1[Researcher ReAct Agent]
      W1[Writer ReAct Agent]
      E1[Evaluator ReAct Agent]
      S1---P1
      S1---R1
      S1---W1
      S1---E1
      State[(Shared Graph State)]
    end

    subgraph A2A-based
      P2[Planner (A2A Agent)]
      R2[Researcher (A2A Agent)]
      W2[Writer (A2A Agent)]
      E2[Evaluator (A2A Agent)]
      Bus[[A2A Protocol (SSE/JSON-RPC)]]
      P2--Bus
      R2--Bus
      W2--Bus
      E2--Bus
    end

    MCPS[(MCP Servers)]
    R1 --> MCPS
    R2 --> MCPS
```
