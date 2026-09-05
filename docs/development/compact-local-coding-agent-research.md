# Compact Local Coding Agents (2026)

Research date: 2026-08-23. Sources are limited to first-party documentation and
source repositories. “Not documented” means that the reviewed primary sources did
not establish the capability; it is not a claim that the capability cannot exist
through an extension or plugin.

## Executive Summary

For a 64K local model controlling FreeCAD MCP, the strongest choices are:

1. **Qwen Code** when exact MCP allowlisting is the priority. It supports
   Ollama and arbitrary OpenAI-compatible endpoints, project instructions, and
   per-server `includeTools`/`excludeTools`, as well as global server allow and
   deny lists.
2. **Continue CLI (`cn`)** when a small, explicit configuration is preferred.
   It supports local models, MCP, rules, and command-line tool allow/ask/exclude
   controls. Its `--readonly` mode is useful for reducing the active tool set.
3. **OpenCode** when the user wants the most inspectable built-in prompt and
   permission model. It supports Ollama/OpenAI-compatible providers, MCP, rules,
   agent-specific prompts, and wildcard tool permissions. It does not document a
   per-MCP-tool schema allowlist, so the MCP server itself should expose a narrow
   FreeCAD surface.

**Crush** is also a strong practical candidate: it supports local providers,
MCP tool disabling, project/global context files, and built-in tool denial. **Pi**
has the smallest explicit default tool surface and excellent CLI allowlists, but
MCP is intentionally not built in and requires an extension. **Goose** supports
MCP and tool filtering and has a source-visible prompt template, but its local
model/tool-calling path may require the Ollama tool shim. **Aider** is not a
candidate for direct FreeCAD MCP control without an external adapter.

No reviewed source publishes a fixed token count for the complete system prompt.
The source evidence below establishes prompt *structure* or fixed sections only;
it must not be read as a token estimate.

## Measured OpenCode Request

A localhost capture proxy inspected OpenCode 1.18.21 requests from an otherwise
empty workspace using the configured 64K Qwen model. The measurement includes
the serialized OpenAI-compatible request as sent to Ollama.

The default agent request contained:

- 18,698 system-message characters.
- 166 tool definitions containing 206,335 serialized schema characters.
- 49,058 input tokens reported by Ollama.
- `reasoning_effort: low` and `max_tokens: 8192`.

An agent-specific permission allowlist retained 38 parametric FreeCAD tools and
denied every other tool. Its request contained:

- 1,487 system-message characters.
- 38 tool definitions containing 44,758 serialized schema characters.
- 10,027 input tokens reported by Ollama.
- The same low reasoning effort and output limit.

This establishes that tool schemas, rather than OpenCode's fixed prose, caused
most of the measured context overhead. OpenCode filters denied tools before
serializing the request, so a deny-by-default agent permission set is sufficient
to reduce the FreeCAD context without changing clients. OpenCode also makes a
separate title-generation request for new sessions; that request used a 2,096
character system prompt and no tools, so it does not inflate the main agent
request.

## Comparison

| Agent | Local model support | MCP support | Custom system prompt | Automatic repo instructions | Restrict tools / MCP schemas | Prompt structure evidence |
| --- | --- | --- | --- | --- | --- | --- |
| OpenCode | Yes: Ollama and generic OpenAI-compatible providers. [Providers](https://opencode.ai/docs/providers/) | Yes: local and remote MCP. [MCP](https://opencode.ai/docs/mcp-servers/) | Yes: configurable agent `prompt` plus `instructions`; see [agents](https://opencode.ai/docs/agents/) and [rules](https://opencode.ai/docs/rules/). | Yes: `AGENTS.md`, parent traversal, global rules, and configured instruction files. [Rules](https://opencode.ai/docs/rules/) | Yes for enable/deny/ask at tool or glob level, including MCP server prefixes. No documented MCP schema field for selecting individual server tools. [Tools](https://opencode.ai/docs/tools/) | Source selects a provider-specific prompt file and builds environment, instructions, skills, and MCP sections: [system.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/system.ts), [prompt files](https://github.com/anomalyco/opencode/tree/dev/packages/opencode/src/session/prompt). MCP docs explicitly warn that schemas add context. |
| Qwen Code | Yes: OpenAI-compatible APIs including local Ollama/vLLM/LM Studio. [Model providers](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/model-providers.md) | Yes: stdio, SSE, and HTTP; configured in `settings.json`. [MCP](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/mcp.md) | CLI customization is documented through `QWEN.md`; the SDK exposes full `systemPrompt` replacement or append, but a CLI flag for replacing the built-in prompt was not established in the reviewed docs. [SDK options](https://github.com/QwenLM/qwen-code/blob/main/packages/sdk-typescript/README.md) | Yes: global/project `QWEN.md`, local project instructions, and `AGENTS.md` compatibility. [Memory](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/memory.md) | **Strongest:** server allow/deny plus per-server `includeTools` and `excludeTools`; SDK also exposes `coreTools`, `allowedTools`, and `excludeTools`. [MCP server developer docs](https://github.com/QwenLM/qwen-code/blob/main/docs/developers/tools/mcp-server.md), [SDK schema](https://github.com/QwenLM/qwen-code/blob/main/packages/sdk-typescript/src/types/queryOptionsSchema.ts) | Source docs describe MCP schema sanitization/registration; the reviewed sources do not publish a fixed complete system-prompt template or token size. |
| Goose | Yes: Ollama/local configuration and OpenAI-compatible providers; Ollama tool shim exists for models without native structured tool calls. [Config](https://github.com/block/goose/blob/main/documentation/docs/guides/config-files.md), [environment variables](https://github.com/block/goose/blob/main/documentation/docs/guides/environment-variables.md) | Yes: MCP is represented as extensions, including stdio, HTTP, and SSE. [Config](https://github.com/block/goose/blob/main/documentation/docs/guides/config-files.md) | Yes: configurable prompt templates are documented. [Prompt templates](https://github.com/block/goose/tree/main/documentation/docs/guides/context-engineering) | Yes by default for `.goosehints` and `AGENTS.md`, with configurable filenames and directory traversal. [Loader source](https://github.com/block/goose/blob/main/crates/goose/src/hints/load_hints.rs) | Yes: extension `available_tools` filters tools; enabled/disabled extensions further limit exposure. No separate MCP JSON-schema projection control was found. [Config](https://github.com/block/goose/blob/main/documentation/docs/guides/config-files.md) | A source-visible Jinja template enumerates extension name, resource support, instructions, and tool-limit warnings: [system.md](https://github.com/block/goose/blob/main/crates/goose/src/prompts/system.md). It is structurally fixed but dynamically populated. |
| Continue CLI | Yes: local Ollama models and custom model endpoints through the shared config. [Ollama](https://docs.continue.dev/customize/model-providers/top-level/ollama), [CLI](https://docs.continue.dev/guides/cli) | Yes in agent mode; MCP servers are configured in `config.yaml` or `.continue/mcpServers`. [MCP](https://docs.continue.dev/customize/deep-dives/mcp) | Yes through configuration/rules and launch-time `--rule`; a single documented “replace all system prompt” CLI flag was not found. [Configuration](https://docs.continue.dev/cli/configuration) | Rules are loaded from Continue configuration; the reviewed CLI docs do not establish automatic loading of arbitrary `AGENTS.md`/`CLAUDE.md` files. | Yes: `--allow`, `--ask`, `--exclude`; `--readonly` limits the session to read-only tools. MCP-server schema field filtering was not established. [CLI quickstart](https://docs.continue.dev/cli/quickstart) | The public CLI sources/docs establish configurable models, rules, and tools, but the reviewed sources do not publish a complete fixed system-prompt template or token size. |
| Crush | Yes: Ollama, llama.cpp, LM Studio, and other local/custom providers. [README: local models](https://github.com/charmbracelet/crush/blob/main/README.md#local-models) | Yes: stdio, HTTP, and SSE. [README: MCPs](https://github.com/charmbracelet/crush/blob/main/README.md#mcps) | Global context files are explicitly described as additions to the system prompt; a general prompt replacement setting was not established. [README: global context](https://github.com/charmbracelet/crush/blob/main/README.md#global-context-files) | Yes: project/global `AGENTS.md`/`CRUSH.md` context and configurable context paths. [README](https://github.com/charmbracelet/crush/blob/main/README.md#global-context-files) | Yes: built-in `permissions deny`, `--disabled-tools` for MCP entries, and `permissions allow`; no MCP schema projection was found. [README](https://github.com/charmbracelet/crush/blob/main/README.md#mcps) | The reviewed README gives the context-loading and tool configuration structure, but no fixed complete system-prompt source or token count. |
| Aider | Yes: local Ollama and generic OpenAI-compatible APIs. [Ollama](https://aider.chat/docs/llms/ollama.html), [OpenAI-compatible](https://aider.chat/docs/llms/openai-compat.html) | **No native MCP client found in the official docs/repository reviewed.** | Yes in practice through read-only convention files and prompt/config options; the reviewed docs emphasize adding files to chat rather than replacing a system prompt. [Conventions](https://aider.chat/docs/usage/conventions.html), [options](https://aider.chat/docs/config/options.html) | No special automatic repo instruction file was established. Conventions can be configured with `read:` in `.aider.conf.yml`. | No MCP schema/tool filtering applies. Built-in editing behavior is controlled through modes and file selection, not MCP. | Aider exposes `--show-prompts` and keeps prompt construction in source, but the reviewed docs/source do not establish a fixed token budget. Its repo map and chat history are additional context, not a fixed system-prompt size. |
| Pi coding agent | Local support through llama.cpp and custom OpenAI/Anthropic-compatible providers. [Providers](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md#providers--models) | Not built in by design; MCP requires an extension. [README philosophy](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md#philosophy) | **Strong:** `--system-prompt`, `--append-system-prompt`, project/global `SYSTEM.md`, and `APPEND_SYSTEM.md`. [README](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md#system-prompt) | Yes: parent/current `AGENTS.md` or `CLAUDE.md`; can be disabled with `--no-context-files`. [Context files](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md#context-files) | **Strong for built-in/extensions:** `--tools`, `--exclude-tools`, `--no-builtin-tools`, `--no-tools`. MCP exposure is extension-defined, so no native MCP schema filter. [CLI tool options](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md#tool-options) | The README states a default four-tool set (`read`, `write`, `edit`, `bash`) and exposes prompt replacement/append controls. Full prompt composition is extension-dependent; no fixed token count is published. |

## FreeCAD MCP Recommendation

The measured OpenCode permission allowlist is the lowest-change option for this
project: it reduced the actual local request from 49,058 to 10,027 input tokens
without changing the MCP server or model provider.

Use **Qwen Code** if configuration-level MCP `includeTools` and `excludeTools`
are preferred over OpenCode agent permissions. Keep `QWEN.md` short because it
is guaranteed startup context and is therefore permanent overhead.

Use **Continue CLI** as the second option when its explicit `--allow`/`--exclude`
workflow is more convenient than editing JSON. Use `--readonly` for inspection
tasks and a small rule file for FreeCAD-specific operating constraints.

Use **OpenCode** when its source-visible prompt composition and permission
wildcards are more valuable than per-server schema filtering. Disable every
unneeded MCP server/tool and configure the FreeCAD MCP prefix explicitly. Its
documentation’s warning that MCP schemas consume context is directly relevant to
a 64K model.

Use **Crush** if the desired configuration is a shell-like `crushrc` and the
server’s tool set can be safely reduced with `--disabled-tools`. Use **Pi** only
if adopting or writing an extension that exposes FreeCAD MCP; its native tool
allowlist and prompt replacement are excellent, but native MCP absence is a real
integration cost. Do not choose **Aider** for direct MCP control without adding a
separate bridge.

### Operational constraints

- Verify that the selected local model supports structured tool calls through the
  chosen API endpoint. Goose documents a tool shim because local models may emit
  text-form tool calls instead of API tool calls.
- Keep the FreeCAD server’s published tool set narrow in addition to client-side
  filtering. Client filters reduce what is sent to the model; they do not reduce
  the server’s own attack surface.
- Do not claim a prompt-token budget from these sources. Measure actual serialized
  requests against the chosen model and tokenizer, including MCP schemas and
  loaded repository instructions.

## Primary Sources

- [OpenCode source repository](https://github.com/anomalyco/opencode)
- [Qwen Code source repository](https://github.com/QwenLM/qwen-code)
- [Goose source repository](https://github.com/block/goose)
- [Continue source repository](https://github.com/continuedev/continue)
- [Crush source repository](https://github.com/charmbracelet/crush)
- [Aider source repository](https://github.com/Aider-AI/aider)
- [Pi coding agent source repository](https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent)
