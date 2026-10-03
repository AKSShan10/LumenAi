"""LangGraph AI workflows: one parent graph, and one subgraph per stage.

    recruitment_graph.py    parent   load_context -> (stage) -> one subgraph -> persist_state

The subgraphs are added with their features:
    pre_interview        CV screening and scoring
    interview_analysis   question and answer analysis
    post_interview       final assessment
"""
