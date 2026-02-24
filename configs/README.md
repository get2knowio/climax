# Bundled Configs

CLImax ships with ready-to-use configs for common CLIs. Use them by name:

```bash
climax run git          # start MCP server with git tools
climax list obsidian    # show all tools in a config
```

All `command` values support `$ENV_VAR` and `~/` expansion at runtime.

---

## git

Common Git version control operations.

| Field | Value |
|-------|-------|
| **Command** | `git` (from PATH) |
| **Category** | `vcs` |
| **Env vars** | None |

**Tools (6):** `git_status`, `git_log`, `git_diff`, `git_branch`, `git_add`, `git_commit`

---

## docker

Docker container and image management. Focuses on read/inspect operations for safety.

| Field | Value |
|-------|-------|
| **Command** | `docker` (from PATH) |
| **Category** | `containers` |
| **Env vars** | None |

**Tools (5):** `docker_ps`, `docker_images`, `docker_logs`, `docker_inspect`, `docker_compose_ps`

---

## claude

Claude Code non-interactive prompt execution via `-p` mode. Prompts are piped via stdin to avoid OS arg length limits.

| Field | Value |
|-------|-------|
| **Command** | `$HOME/.local/bin/claude` |
| **Category** | `ai` |
| **Env vars** | `$HOME` (used in command path) |

**Tools (4):** `claude_ask`, `claude_ask_with_model`, `claude_ask_json`, `claude_ask_with_system_prompt`

---

## obsidian

Obsidian vault management via the [Obsidian CLI](https://github.com/Obsidian-CLI/obsidian-cli). Uses inline flag syntax (`flag: "key="`) for Obsidian's `key=value` argument format.

| Field | Value |
|-------|-------|
| **Command** | `Obsidian` (from PATH) |
| **Category** | `productivity` |
| **Env vars** | None |

**Tools (53):**

| Group | Tools |
|-------|-------|
| Vault info | `obsidian_vault`, `obsidian_vaults`, `obsidian_version` |
| File browsing | `obsidian_files`, `obsidian_folders`, `obsidian_file`, `obsidian_folder`, `obsidian_recents` |
| Read & write | `obsidian_read`, `obsidian_create`, `obsidian_write`, `obsidian_append`, `obsidian_prepend`, `obsidian_move`, `obsidian_rename`, `obsidian_delete`, `obsidian_wordcount` |
| Search | `obsidian_search`, `obsidian_search_context` |
| Knowledge graph | `obsidian_links`, `obsidian_backlinks`, `obsidian_tags`, `obsidian_tag`, `obsidian_aliases`, `obsidian_outline`, `obsidian_orphans`, `obsidian_deadends`, `obsidian_unresolved` |
| Properties | `obsidian_properties`, `obsidian_property_read`, `obsidian_property_set`, `obsidian_property_remove` |
| Tasks | `obsidian_tasks`, `obsidian_task` |
| Daily notes | `obsidian_daily_read`, `obsidian_daily_path`, `obsidian_daily_append`, `obsidian_daily_prepend` |
| Bookmarks | `obsidian_bookmarks`, `obsidian_bookmark` |
| Templates | `obsidian_templates`, `obsidian_template_read` |
| Bases | `obsidian_bases`, `obsidian_base_query`, `obsidian_base_views` |
| Plugins | `obsidian_plugins`, `obsidian_plugins_enabled` |
| Commands | `obsidian_commands`, `obsidian_command` |
| Open | `obsidian_open` |
| Sync | `obsidian_sync_status` |
| History | `obsidian_history`, `obsidian_history_read` |
