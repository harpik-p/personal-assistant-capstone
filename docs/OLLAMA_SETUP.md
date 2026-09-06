# Free local model setup with Ollama

Ollama mode runs the email interpretation model on your Mac. It has no per-request API charge and does not send email text to OpenAI. Model files require local disk space, and inference speed depends on the Mac.

## 1. Install Ollama

Download and install Ollama for macOS from <https://ollama.com/download>.

After opening the Ollama application, confirm the command is available:

```bash
ollama --version
```

## 2. Download the default model

```bash
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

The default reasoning model is deliberately modest for a local capstone demonstration. The smaller `nomic-embed-text` model provides semantic long-term memory retrieval. It runs locally and its vectors are cached in SQLite.

## 3. Test with sample data

```bash
cd /Users/aaroncolak/.codex/.chatgpt-projects/g-p-6a99ed7f59d88191b2ab7c9a1ef0abc0
source .venv/bin/activate
personal-assistant-mcp-demo --source demo --reasoning ollama
```

## 4. Process Gmail locally

```bash
ASSISTANT_DB_PATH=assistant.db personal-assistant-mcp-demo --source gmail --reasoning ollama
```

## Configuration

Defaults:

```bash
export OLLAMA_BASE_URL="http://127.0.0.1:11434"
export OLLAMA_MODEL="qwen3:4b"
export OLLAMA_EMBEDDING_MODEL="nomic-embed-text"
export ASSISTANT_MEMORY_MODE="ollama"
```

The assistant requests a JSON-schema-constrained response with temperature zero. Returned fields are validated before the result reaches duplicate detection and the safety policy. If email reasoning times out, conservative rules provide a fallback. If semantic retrieval is unavailable, memory lookup falls back to keyword matching.

## Privacy boundary

In Ollama mode, Gmail content is sent only to the Ollama service at the configured address. Keep `OLLAMA_BASE_URL` set to `127.0.0.1` to ensure it remains local. Avoid installing untrusted models, and review each model's license before redistributing it.
