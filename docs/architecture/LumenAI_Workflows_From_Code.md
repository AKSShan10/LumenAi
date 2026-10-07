# LumenAI workflows, drawn from the code

Made by `backend/scripts/print_workflows.py`. Do not edit by hand: run the script again after a change.
A solid arrow is always followed. A dotted arrow is a choice made by the code at that step.

## Job description workflow

Code: `backend/app/graphs/job_description_graph.py`

Steps: `retrieve_documents`, `write_draft`, `check_draft`, `revise_draft`, `log_run`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	retrieve_documents(retrieve_documents)
	write_draft(write_draft)
	check_draft(check_draft)
	revise_draft(revise_draft)
	log_run(log_run)
	__end__([<p>__end__</p>]):::last
	__start__ --> retrieve_documents;
	check_draft -.-> log_run;
	check_draft -.-> revise_draft;
	retrieve_documents --> write_draft;
	revise_draft --> check_draft;
	write_draft --> check_draft;
	log_run --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Assistant agent (the chatbot)

Code: `backend/app/graphs/assistant_agent.py`

Steps: `agent`, `tools`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	agent(agent)
	tools(tools)
	__end__([<p>__end__</p>]):::last
	__start__ --> agent;
	agent -.-> __end__;
	agent -.-> tools;
	tools --> agent;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
