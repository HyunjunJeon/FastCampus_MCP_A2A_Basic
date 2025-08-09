# Step 3 — State

관련 Step: [../../steps/step3.md](../../steps/step3.md)

```mermaid
stateDiagram-v2
    state "MCP-only (LangGraph)" as MCP {
        [*] --> Supervisor
        Supervisor --> Subgraphs
        state Subgraphs {
            Planner --> Researcher --> Writer --> Evaluator
        }
        Subgraphs --> SharedState
        note right of SharedState: Shared state grows\n(deep nesting)
        SharedState --> [*]
    }

    state "A2A" as A2A {
        [*] --> Agents
        state Agents {
            Planner2
            Researcher2
            Writer2
            Evaluator2
        }
        Agents --> MessageBus
        note right of MessageBus: Standard A2A messaging
        MessageBus --> [*]
    }
```
