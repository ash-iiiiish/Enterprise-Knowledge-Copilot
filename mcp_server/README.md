# MCP tool layer

`server.py` defines the tools with FastMCP; `client.py` lets the LLM pick one and
calls it in-process. Task tools are thin wrappers over `db/task_repository.py`,
the same code the REST API uses, so chat and the Tasks page behave identically.

| Tool | Purpose |
|------|---------|
| `assign_task` | Create tasks for people / a department / everyone and notify them |
| `query_tasks` | Filter tasks by person, status, priority, overdue, due or created dates |
| `update_task` | Change status (assignee) or priority / due date / assignee (whoever assigned it, HR) |
| `get_employee_details`, `list_employees` | Directory lookups |
| `fetch_company_policy`, `search_internal_knowledge` | Small built-in knowledge |
| `web_search` | DuckDuckGo fallback |

**Identity is never taken from the model.** Every task tool has an `actor_id`
parameter. The client hides it from the LLM's tool catalogue and always sets it
from the signed-in user, and the repository enforces permissions again on the
server, so a prompt cannot make the assistant act as someone else.

Add a tool by writing another `@mcp.tool` function. It appears in the router's
catalogue automatically. Put it in `WRITE_TOOLS` if it changes data (those skip
answer-verification and are never retried).
