---
name: llm-prompting-engineer
description: "Designs system prompts, shapes specialized agent personas, configures output schemas, and sets up LLM reasoning and retry behaviors."
---

# LLM Prompting Engineer Skill

This skill provides rules and best practices for configuring prompt structures, managing French system instructions, defining specialized clinical personas, and building self-correcting RAG interactions.

## Guidelines & Personas

### 1. French Language Consistency
By default, the Oncoflow web interface and patient records are in French. The agent must interact in French seamlessly without explaining its language choice.
- **Rule**: Standard instruction headers must start with:
  > `Answer in French language, not mention it in the answer.`

### 2. Multi-specialty Clinical Personas
Oncoflow supports three specific cancer specialty experts. System prompts must be structured to match:
- **Pancreatic Cancer (pancreas expert)**: System prompt must focus strictly on pancreas diseases and rely on scientific evidence from `TNCDPANCREAS.pdf`.
- **Esophageal Cancer (oesophagus expert)**: Focus strictly on esophagus diseases and scientific evidence from `TNCDOESOPHAGE.pdf`.
- **Hepatocellular Cancer (hepatocellular expert)**: Focus strictly on liver/hepatocellular diseases and scientific evidence from `TNCDCHC.pdf`.

### 3. Handling Output Formats & Parsing Failures
Ensure Pydantic schemas are strictly respected. If LLMs fail to match the structure, utilize `ToolRetryMiddleware` and `ModelRetryMiddleware` configured with standard backoffs:
```python
middleware=[
    ToolRetryMiddleware(max_retries=3, backoff_factor=2.0, initial_delay=1.0),
    ModelRetryMiddleware(max_retries=3, backoff_factor=2.0, initial_delay=1.0)
]
```
Ensure structured tool strategies have proper error handlers:
```python
response_format=ToolStrategy(schema=self.output_format, handle_errors=True)
```
