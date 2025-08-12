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

    subgraph A2A Agents
      DR[DeepResearch Agent (8090)]
      RES[Researcher Agent (8091)]
      SUP[Supervisor Agent (8092)]
    end

    Client[HITL Viewer]

    Client -- WS --> API
    API -- broadcasts --> UI
    Manager -- pub/sub --> WS
    DR -- requests --> Manager
    Manager -- persists --> Store
    API -- health/card --> Client
```
