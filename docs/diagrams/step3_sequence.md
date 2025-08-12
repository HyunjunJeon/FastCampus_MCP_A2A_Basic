# Step 3 — Sequence

관련 Step: [../../steps/step3.md](../../steps/step3.md)

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant LG as LangGraph (MCP-only)
    participant A2AD as Deep/HITL A2A (8090)
    participant A2AR as Researcher A2A (8091)
    participant A2AS as Supervisor A2A (8092)

    U->>LG: Query (same topic)
    LG-->>U: Final Report

    U->>A2AS: Query (same topic)
    A2AS->>A2AR: Delegate research
    A2AR-->>A2AS: Findings
    A2AS->>A2AD: Orchestrate final report
    A2AD-->>U: Final Report (A2A)
```
