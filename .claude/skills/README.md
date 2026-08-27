# Project skills

## superpowers

The skills in this directory (`brainstorming`, `dispatching-parallel-agents`,
`executing-plans`, `finishing-a-development-branch`, `receiving-code-review`,
`requesting-code-review`, `subagent-driven-development`,
`systematic-debugging`, `test-driven-development`, `using-git-worktrees`,
`using-superpowers`, `verification-before-completion`, `writing-plans`,
`writing-skills`) are vendored from the [superpowers](https://github.com/obra/superpowers)
project by Jesse Vincent, MIT licensed (see `SUPERPOWERS-LICENSE`).

They cover TDD, debugging, planning, and collaboration workflows for use
with Claude Code in this repository. Plugin-only features (hooks, the
`/plugin` marketplace metadata) were not copied — only the skill content
itself.

## Context7

The `context7` MCP server (project `.mcp.json`) gives Claude Code access to
up-to-date library/framework documentation via
[Upstash Context7](https://github.com/upstash/context7). It runs on demand
via `npx` — no extra install step required, though setting a `CONTEXT7_API_KEY`
env var raises the free rate limit.
