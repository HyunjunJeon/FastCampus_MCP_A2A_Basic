# Step 1 — Architecture

관련 Step: [../../steps/step1.md](../../steps/step1.md)

```mermaid
graph TD
    subgraph App
        A[LangGraph Agent]
        B[LangChain-MCP Adapters\n(MultiServerMCPClient)]
        L[LLM]
    end
    subgraph MCP
        T[Tavily MCP]
        X[arXiv MCP]
        S[Serper MCP]
    end

    A -- binds tools --> L
    A -- obtains tools --> B
    B -- HTTP/JSON-RPC --> T
    B -- HTTP/JSON-RPC --> X
    B -- HTTP/JSON-RPC --> S
```
