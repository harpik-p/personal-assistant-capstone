# Optional model reasoning setup

The assistant runs in deterministic `rules` mode by default. This keeps the demo reproducible and lets the MCP/Gmail workflow run without sending email text to a model.

For richer interpretation of implicit tasks and ambiguous language, enable the optional OpenAI reasoning adapter. It uses structured output so the model must return the expected fields before the safety policy can evaluate an action.

## 1. Install the optional dependency

```bash
source .venv/bin/activate
python -m pip install -e '.[llm]'
```

## 2. Configure credentials

Set an OpenAI API key and a model that is available to your API project:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="your-model-name"
```

Do not put the API key in source code, `README.md`, or any committed file. A ChatGPT subscription and API billing are separate services.

## 3. Run through MCP

Test with the sample inbox first:

```bash
personal-assistant-mcp-demo --source demo --reasoning openai
```

Then use the read-only Gmail source:

```bash
ASSISTANT_DB_PATH=assistant.db personal-assistant-mcp-demo --source gmail --reasoning openai
```

## Data and safety behavior

In OpenAI reasoning mode, the text of the latest Gmail thread (up to five messages) is sent to the configured model API for interpretation. The response must contain a summary, action classification, optional task title and date, confidence, and rationale.

The model cannot directly write tasks or memories. Its structured proposal still passes through duplicate detection, confidence thresholds, the approval queue, and audit logging. Rules mode remains available as an offline fallback:

```bash
personal-assistant-mcp-demo --source gmail --reasoning rules
```
