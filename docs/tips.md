## Background
Thanks for checking the official source. Based on it, the temporary suspension of Fable 5 / Mythos 5 under a U.S. government export-control directive appears to be factual. Per Anthropic's statement, the U.S. government — citing national security authority — ordered a full access block on Fable 5 and Mythos 5 for foreign-national users (including Anthropic employees), while explicitly noting that access to other Anthropic models is unaffected.

On the question of "is Opus the progenitor," the statement itself says nothing about lineage. On safety, it explains that Fable's safeguards were substantially strengthened relative to the broader industry (including other vendors), and that a multi-layered defense strategy was adopted for jailbreak resistance. Claims like "fallback to Opus 4.8" or "designed to migrate from Opus" come from secondary sources; no direct lineage can be confirmed from the official statement. So it seems premature to assert that "Opus is the progenitor of Fable."

---
## Main topic
On the main topic — "preparing for the subscription → usage-based billing shift, leaving in place what we can do now" — given the current state (ai-agent-cli, claude_docs, CLAUDE.md/Skills setup), these directions seem realistic.

### **1. Abstract the model invocation**
If the LLM-invocation layer of ai-agent-cli is structured so the model ID can be switched via environment variables / config files, the cost of switching "Opus → Sonnet → local LLM" drops to nearly zero the moment the billing model changes. This also acts as insurance against "specific-model dependency risk," like the current Fable 5 suspension.

### **2. Use today's high-performance models as a "teacher" and turn that into an asset**
Under usage-based billing, hitting a full-performance model every time gets expensive. While still on the subscription, build out the briefing-generation and report-creation logic with a high-performance model, and lock in its output patterns as prompt templates, Skills, and few-shot examples. That makes it easier to preserve quality later even after swapping in cheaper models (Haiku-class or local Ollama).

### **3. Partially migrate to a local RAG / Ollama setup**
The Mac M4 Air already runs an Ollama + LangChain + FAISS setup, so deterministic work — formatting ticker information, formatting/posting to Notion/Discord — can be shifted to local models or rule-based logic, leaving only the parts that genuinely need reasoning (geopolitical analysis, portfolio-impact assessment) on API calls. Sorting out this split now keeps the per-unit cost impact down after the move to usage-based billing.

### **4. Make usage visible**
To estimate the cost impact after moving to usage-based billing, start logging token usage per task in ai-agent-cli now. That reveals which tasks are high-cost ahead of time, so you can prioritize what to optimize first.

Where would you imagine starting? For example, designing the "model-abstraction refactoring" together could be a good first step.
