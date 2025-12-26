# Sample Agents

All the agents in this directory are samples built on different frameworks highlighting different capabilities. Each agent runs as a standalone A2A server.

Each agent can be run as its own A2A server with the instructions on its README. By default, each will run on a separate port on localhost (you can use command line arguments to override).

## Agents Directory

* [**AG2 MCP Agent with A2A Protocol**](/samples/python/agents/ag2/README.md)  
Demonstrates an MCP-enabled agent built with [AG2](https://github.com/ag2ai/ag2) that is exposed through the A2A protocol.

* [**LangGraph**](/samples/python/agents/langgraph/README.md)  
Sample agent which can convert currency using tools. Showcases multi-turn interactions, tool usage, and streaming updates.

* [**Enterprise Data Agent**](/samples/python/agents/mindsdb/README.md)  
Sample agent which can answer questions from any database, datawarehouse, app. - Powered by Gemini 2.5 flash + MindsDB.

* [**travel planner Agent**](/samples/python/agents/travel_planner_agent/README.md)  
A travel assistant demo implemented based on Google's official [a2a-python](https://github.com/google/a2a-python) SDK, And Implemented through the A2A protocol.

* [**Any-Agent Adversarial Multi-Agent**](/samples/python/agents/any_agent_adversarial_multiagent/README.md)  
Demonstrates an adversarial multi-agent system with competing attacker and defender agents using the A2A protocol and any-agent library.

## Disclaimer

Important: The sample code provided is for demonstration purposes and illustrates the
mechanics of the Agent-to-Agent (A2A) protocol. When building production applications,
it is critical to treat any agent operating outside of your direct control as a
potentially untrusted entity.

All data received from an external agent—including but not limited to its AgentCard,
messages, artifacts, and task statuses—should be handled as untrusted input. For
example, a malicious agent could provide an AgentCard containing crafted data in its
fields (e.g., description, name, skills.description). If this data is used without
sanitization to construct prompts for a Large Language Model (LLM), it could expose
your application to prompt injection attacks.  Failure to properly validate and
sanitize this data before use can introduce security vulnerabilities into your
application.

Developers are responsible for implementing appropriate security measures, such as
input validation and secure handling of credentials to protect their systems and users.
