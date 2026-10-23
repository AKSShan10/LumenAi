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
	__start__([start]):::first
	retrieve_documents(retrieve_documents)
	write_draft(write_draft)
	check_draft(check_draft)
	revise_draft(revise_draft)
	log_run(log_run)
	__end__([end]):::last
	__start__ --> retrieve_documents;
	check_draft -.-> log_run;
	check_draft -.-> revise_draft;
	retrieve_documents --> write_draft;
	revise_draft --> check_draft;
	write_draft --> check_draft;
	log_run --> __end__;
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
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
	__start__([start]):::first
	check_job(check_job)
	ask_person(ask_person)
	publish(publish)
	save_result(save_result)
	__end__([end]):::last
	__start__ --> check_job;
	ask_person -.-> publish;
	ask_person -.-> save_result;
	check_job -.-> ask_person;
	check_job -.-> save_result;
	publish --> save_result;
	save_result --> __end__;
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
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
	__start__([start]):::first
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
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
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
	__start__([start]):::first
	write_draft(write_draft)
	check_draft(check_draft)
	save_draft(save_draft)
	ask_person(ask_person)
	send_email(send_email)
	save_result(save_result)
	__end__([end]):::last
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
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
```

## Q&A analysis workflow (after the interview, one run per interview)

Code: `backend/app/graphs/qa_analysis_graph.py`

Steps: `load_transcript`, `segment_qa_pairs`, `classify_requirements`, `evaluate_relevance`, `evaluate_accuracy`, `evaluate_completeness`, `evaluate_articulation`, `evaluate_problem_solving`, `evaluate_depth`, `merge_evaluation`, `detect_requirement_gaps`, `build_scorecard`, `save`, `failed`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([start]):::first
	load_transcript(load_transcript)
	segment_qa_pairs(segment_qa_pairs)
	classify_requirements(classify_requirements)
	evaluate_relevance(evaluate_relevance)
	evaluate_accuracy(evaluate_accuracy)
	evaluate_completeness(evaluate_completeness)
	evaluate_articulation(evaluate_articulation)
	evaluate_problem_solving(evaluate_problem_solving)
	evaluate_depth(evaluate_depth)
	merge_evaluation(merge_evaluation)
	detect_requirement_gaps(detect_requirement_gaps)
	build_scorecard(build_scorecard)
	save(save)
	failed(failed)
	__end__([end]):::last
	__start__ --> load_transcript;
	build_scorecard --> save;
	classify_requirements -.-> evaluate_accuracy;
	classify_requirements -.-> evaluate_articulation;
	classify_requirements -.-> evaluate_completeness;
	classify_requirements -.-> evaluate_depth;
	classify_requirements -.-> evaluate_problem_solving;
	classify_requirements -.-> evaluate_relevance;
	classify_requirements -.-> failed;
	detect_requirement_gaps --> build_scorecard;
	evaluate_accuracy --> merge_evaluation;
	evaluate_articulation --> merge_evaluation;
	evaluate_completeness --> merge_evaluation;
	evaluate_depth --> merge_evaluation;
	evaluate_problem_solving --> merge_evaluation;
	evaluate_relevance --> merge_evaluation;
	load_transcript -.-> failed;
	load_transcript -. go .-> segment_qa_pairs;
	merge_evaluation -. go .-> detect_requirement_gaps;
	merge_evaluation -.-> failed;
	segment_qa_pairs -. go .-> classify_requirements;
	segment_qa_pairs -.-> failed;
	failed --> __end__;
	save --> __end__;
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
```

## Assessment workflow (post-interview, one run per candidate)

Code: `backend/app/graphs/assessment_graph.py`

Steps: `load_all_results`, `analyze_strengths`, `analyze_weaknesses`, `evidence_gaps`, `recommended_areas`, `merge_assessment`, `validate_traceability`, `repair_assessment`, `generate_report`, `save`, `failed`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([start]):::first
	load_all_results(load_all_results)
	analyze_strengths(analyze_strengths)
	analyze_weaknesses(analyze_weaknesses)
	evidence_gaps(evidence_gaps)
	recommended_areas(recommended_areas)
	merge_assessment(merge_assessment)
	validate_traceability(validate_traceability)
	repair_assessment(repair_assessment)
	generate_report(generate_report)
	save(save)
	failed(failed)
	__end__([end]):::last
	__start__ --> load_all_results;
	analyze_strengths --> merge_assessment;
	analyze_weaknesses --> merge_assessment;
	evidence_gaps --> merge_assessment;
	generate_report -.-> failed;
	generate_report -. go .-> save;
	load_all_results -.-> analyze_strengths;
	load_all_results -.-> analyze_weaknesses;
	load_all_results -.-> evidence_gaps;
	load_all_results -.-> failed;
	load_all_results -.-> recommended_areas;
	merge_assessment -.-> failed;
	merge_assessment -. go .-> validate_traceability;
	recommended_areas --> merge_assessment;
	repair_assessment --> validate_traceability;
	validate_traceability -.-> generate_report;
	validate_traceability -.-> repair_assessment;
	failed --> __end__;
	save --> __end__;
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
```

## CV claim verification workflow (after the interview, one run per candidate)

Code: `backend/app/graphs/claim_check_graph.py`

Steps: `load_inputs`, `extract_claims`, `check_cv_quotes`, `compare_claims`, `check_interview_quotes`, `save`, `failed`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([start]):::first
	load_inputs(load_inputs)
	extract_claims(extract_claims)
	check_cv_quotes(check_cv_quotes)
	compare_claims(compare_claims)
	check_interview_quotes(check_interview_quotes)
	save(save)
	failed(failed)
	__end__([end]):::last
	__start__ --> load_inputs;
	check_cv_quotes --> compare_claims;
	check_interview_quotes --> save;
	compare_claims -. go .-> check_interview_quotes;
	compare_claims -.-> failed;
	extract_claims -. go .-> check_cv_quotes;
	extract_claims -.-> failed;
	load_inputs -. go .-> extract_claims;
	load_inputs -.-> failed;
	failed --> __end__;
	save --> __end__;
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
```

## Talent pool invitation workflow (one run per person; a person sends)

Code: `backend/app/graphs/talent_invite_graph.py`

Steps: `load_facts`, `write_draft`, `check_draft`, `standard_text`, `finish`

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([start]):::first
	load_facts(load_facts)
	write_draft(write_draft)
	check_draft(check_draft)
	standard_text(standard_text)
	finish(finish)
	__end__([end]):::last
	__start__ --> load_facts;
	check_draft -.-> finish;
	check_draft -.-> standard_text;
	check_draft -.-> write_draft;
	load_facts --> write_draft;
	standard_text --> finish;
	write_draft --> check_draft;
	finish --> __end__;
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
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
	__start__([start]):::first
	agent(agent)
	tools(tools)
	pre_model_hook(pre_model_hook)
	__end__([end]):::last
	__start__ --> pre_model_hook;
	agent -.-> __end__;
	agent -.-> tools;
	pre_model_hook --> agent;
	tools --> pre_model_hook;
	classDef default fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434,line-height:1.2
	classDef first fill:#f2f0ff,stroke:#6b5fd6,color:#1c2434
	classDef last fill:#bfb6fc,stroke:#6b5fd6,color:#1c2434
```
