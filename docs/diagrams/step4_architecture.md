# Step 4 — Architecture

관련 Step: [../../steps/step4.md](../../steps/step4.md)

```mermaid
graph TD
    subgraph HITL Web/API
      API[FastAPI REST/WS]
      WS[WebSocket Manager]
      UI[Static Dashboard]
    end

    subgraph HITL Core
      Manager[HITLManager]
      Store[Redis-based ApprovalStorage]
    end

    subgraph DeepResearch
      DR[DeepResearch Agent (A2A)]
    end

    Client[HITL Viewer]

    Client -- WS --> API
    API -- broadcasts --> UI
    Manager -- pub/sub --> WS
    DR -- requests --> Manager
    Manager -- persists --> Store
    API -- health/card --> Client
```
