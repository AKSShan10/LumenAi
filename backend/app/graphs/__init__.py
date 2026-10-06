"""LangGraph AI workflows: one parent graph, and one subgraph per stage.

    recruitment_graph.py    parent   load_context -> (stage) -> one subgraph -> persist_state

    job_description_graph.py         retrieve_documents -> write_draft -> check_draft -> (revise_draft) -> log_run
                                     writes a job profile from a short prompt, using company documents (RAG)

    job_post_graph.py                write_post -> check_post -> (revise_post) -> log_run
                                     writes the Telegram post for an approved job

The subgraphs are added with their features:
    pre_interview        CV screening and scoring
    interview_analysis   question and answer analysis
    post_interview       final assessment
"""
