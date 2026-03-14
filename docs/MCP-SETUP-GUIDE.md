# MCP Setup Guide for Cursor

How to add the **GitHub** and **Atlassian (Jira + Confluence)** MCP servers to your Cursor so the AI assistant can interact with repos, PRs, Jira tickets, and Confluence pages.

---

## Prerequisites

| Requirement | How to get it |
|-------------|---------------|
| **GitHub Personal Access Token** | GitHub → Settings → Developer settings → Personal access tokens → Generate new token. Scopes needed: `repo`, `read:org`. |
| **Jira / Confluence API Token** | [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → Create API token. |
| **Node.js (npx)** | Install via [volta](https://volta.sh) or [nvm](https://github.com/nvm-sh/nvm). Needed for the GitHub MCP server. |
| **Docker** | Install [Docker Desktop](https://www.docker.com/products/docker-desktop/). Needed for the Atlassian MCP server. |

---

## 1. Open Cursor MCP settings

Go to **Cursor Settings → MCP** (or edit `~/.cursor/mcp.json` directly).

---

## 2. Add the GitHub MCP server

```json
{
  "github-mcp": {
    "command": "npx",
    "args": [
      "-y",
      "@modelcontextprotocol/server-github"
    ],
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_GITHUB_PAT>"
    }
  }
}
```

> **Note:** If you use Volta, replace `"npx"` with the full path to your npx binary (e.g. `"/Users/<you>/.volta/bin/npx"`).

### What it gives you

- Search repos, issues, PRs
- Read file contents from GitHub
- Create/update issues and PRs
- List branches, commits, tags

---

## 3. Add the Atlassian MCP server (Jira + Confluence)

```json
{
  "mcp-atlassian": {
    "command": "docker",
    "args": [
      "run", "-i", "--rm",
      "-e", "CONFLUENCE_URL",
      "-e", "CONFLUENCE_USERNAME",
      "-e", "CONFLUENCE_API_TOKEN",
      "-e", "JIRA_URL",
      "-e", "JIRA_USERNAME",
      "-e", "JIRA_API_TOKEN",
      "ghcr.io/sooperset/mcp-atlassian:latest"
    ],
    "env": {
      "CONFLUENCE_URL": "https://floqast.atlassian.net/wiki",
      "CONFLUENCE_USERNAME": "<YOUR_EMAIL>@floqast.com",
      "CONFLUENCE_API_TOKEN": "<YOUR_ATLASSIAN_API_TOKEN>",
      "JIRA_URL": "https://floqast.atlassian.net",
      "JIRA_USERNAME": "<YOUR_EMAIL>@floqast.com",
      "JIRA_API_TOKEN": "<YOUR_ATLASSIAN_API_TOKEN>"
    }
  }
}
```

> The same API token works for both Jira and Confluence.

### What it gives you

- Search and read Jira issues (tickets, Epics, Stories)
- Create/update Jira issues
- Search and read Confluence pages
- Create/update Confluence pages

---

## 4. Full `mcp.json` example

Your `~/.cursor/mcp.json` should look like this (merge with any existing servers):

```json
{
  "mcpServers": {
    "github-mcp": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_GITHUB_PAT>"
      }
    },
    "mcp-atlassian": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "CONFLUENCE_URL",
        "-e", "CONFLUENCE_USERNAME",
        "-e", "CONFLUENCE_API_TOKEN",
        "-e", "JIRA_URL",
        "-e", "JIRA_USERNAME",
        "-e", "JIRA_API_TOKEN",
        "ghcr.io/sooperset/mcp-atlassian:latest"
      ],
      "env": {
        "CONFLUENCE_URL": "https://floqast.atlassian.net/wiki",
        "CONFLUENCE_USERNAME": "<YOUR_EMAIL>@floqast.com",
        "CONFLUENCE_API_TOKEN": "<YOUR_ATLASSIAN_API_TOKEN>",
        "JIRA_URL": "https://floqast.atlassian.net",
        "JIRA_USERNAME": "<YOUR_EMAIL>@floqast.com",
        "JIRA_API_TOKEN": "<YOUR_ATLASSIAN_API_TOKEN>"
      }
    }
  }
}
```

---

## 5. Verify

1. Restart Cursor after saving `mcp.json`.
2. Open **Cursor Settings → MCP** — both servers should show a green status.
3. Test it: ask Cursor something like _"List open PRs in FloQastInc/close"_ or _"Get the description of CLOSE-8615 from Jira"_.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| GitHub MCP won't start | Make sure `npx` is in your PATH. Run `which npx` in terminal to verify. If using Volta, use the full path. |
| Atlassian MCP won't start | Make sure Docker Desktop is running. Run `docker run --rm ghcr.io/sooperset/mcp-atlassian:latest --help` to test. |
| "Forbidden" / 401 errors | Your API token is expired or has insufficient permissions. Regenerate it. |
| Server shows red in Cursor | Check the MCP server logs in Cursor's output panel (View → Output → select the MCP server). |

---

## Security reminders

- **Never share your tokens** — each person generates their own.
- **Never commit tokens** to git. If you accidentally do, revoke and regenerate immediately.
- Tokens should have the **minimum permissions** needed (read-only if you only need to read).
