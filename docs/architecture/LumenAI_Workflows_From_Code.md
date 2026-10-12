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

## Job posting workflow (pauses for the interviewer's Yes or No)

Code: `backend/app/graphs/job_post_graph.py`

Steps: `check_job`, `ask_person`, `publish`, `save_result`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	check_job(check_job)
	ask_person(ask_person)
	publish(publish)
	save_result(save_result)
	__end__([<p>__end__</p>]):::last
	__start__ --> check_job;
	ask_person -.-> publish;
	ask_person -.-> save_result;
	check_job -.-> ask_person;
	check_job -.-> save_result;
	publish --> save_result;
	save_result --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## CV screening workflow (pre-interview subgraph, one run per CV)

Code: `backend/app/graphs/cv_screening_graph.py`

Steps: `parse_cv`, `validate_extraction`, `ocr_once`, `needs_review`, `extract_profile`, `match_requirements`, `justifications`, `score_sections`, `check_quotes`, `ats_match`, `combine_score`, `save_result`, `hr_review`, `apply_decision`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	parse_cv(parse_cv)
	validate_extraction(validate_extraction)
	ocr_once(ocr_once)
	needs_review(needs_review)
	extract_profile(extract_profile)
	match_requirements(match_requirements)
	justifications(justifications)
	score_sections(score_sections)
	check_quotes(check_quotes)
	ats_match(ats_match)
	combine_score(combine_score)
	save_result(save_result)
	hr_review(hr_review)
	apply_decision(apply_decision)
	__start__ -.-> hr_review;
	__start__ -.-> parse_cv;
	apply_decision --> hr_review;
	ats_match --> combine_score;
	check_quotes --> ats_match;
	combine_score --> save_result;
	extract_profile -.-> match_requirements;
	extract_profile -.-> needs_review;
	hr_review --> apply_decision;
	justifications -.-> save_result;
	justifications -.-> score_sections;
	match_requirements --> justifications;
	needs_review --> save_result;
	ocr_once --> validate_extraction;
	parse_cv --> validate_extraction;
	save_result --> hr_review;
	score_sections -.-> check_quotes;
	score_sections -.-> save_result;
	validate_extraction -.-> extract_profile;
	validate_extraction -.-> needs_review;
	validate_extraction -.-> ocr_once;
	extract_profile -.-> extract_profile;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Interview invitation workflow (pauses until the interviewer sends)

Code: `backend/app/graphs/invitation_graph.py`

Steps: `write_draft`, `check_draft`, `save_draft`, `ask_person`, `send_email`, `save_result`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	write_draft(write_draft)
	check_draft(check_draft)
	save_draft(save_draft)
	ask_person(ask_person)
	send_email(send_email)
	save_result(save_result)
	__end__([<p>__end__</p>]):::last
	__start__ --> write_draft;
	ask_person -.-> send_email;
	ask_person -.-> write_draft;
	check_draft -.-> save_draft;
	check_draft -.-> write_draft;
	save_draft --> ask_person;
	save_result --> ask_person;
	send_email --> save_result;
	write_draft --> check_draft;
	ask_person -.-> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Assistant agent (the chatbot)

Code: `backend/app/graphs/assistant_agent.py`

Steps: `agent`, `tools`, `pre_model_hook`

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
	pre_model_hook(pre_model_hook)
	__end__([<p>__end__</p>]):::last
	__start__ --> pre_model_hook;
	agent -.-> __end__;
	agent -.-> tools;
	pre_model_hook --> agent;
	tools --> pre_model_hook;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
