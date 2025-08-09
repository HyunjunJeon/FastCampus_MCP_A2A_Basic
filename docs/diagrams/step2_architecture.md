# Step 2 — Architecture

관련 Step: [../../steps/step2.md](../../steps/step2.md)

```mermaid
graph TD
    subgraph A2A Server
      AC[/.well-known/agent-card.json]
      App[Starlette App]
      Exec[LangGraphWrappedA2AExecutor]
    end
    Graph[LangGraph Graph]
    Client[A2A Client]

    Client -- HTTP/SSE --> App
    App -- uses --> Exec
    Exec -- calls --> Graph
    App -- serves --> AC
```
