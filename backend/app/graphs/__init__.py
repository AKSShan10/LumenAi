"""LangGraph: the AI workflow and the AI agent.

    job_description_graph.py         a workflow (we wrote the order of the steps):
                                     retrieve_documents -> write_draft -> check_draft -> (revise_draft) -> log_run
                                     writes a job profile from a short prompt, using company documents (RAG)
                                     job_description_prompts.py holds its instructions

    cv_screening_graph.py            a workflow: load_cv -> parse_cv (AI, once more if the answer is bad)
                                     -> match_requirements -> decide -> log_run
                                     checks one CV against the job's requirements; cv_screening_prompts.py

    assistant_agent.py               an agent (the AI chooses the next step): agent <-> tools, until it can answer
                                     assistant_prompts.py holds its rules

Later features add their own workflows here (question and answer analysis, final assessment).
"""
