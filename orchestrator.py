from gemini_service import (
    generate_project_ai,
    generate_projects_ai,
    recommend_technologies_ai,
    generate_scenario_ai,
    match_interns_ai,
    track_project_progress_ai,
    analyze_project_health_ai,
    evaluate_submission_ai,
    generate_feedback_ai,
    copilot_response_ai,
    validate_document_structure_ai
)
from rag_service import run_rag_pipeline

class MentoraOrchestrator:
    """
    LangGraph-inspired Multi-Agent Routing Engine
    Orchestrates specialized subagents based on user intent and workflow context.
    """

    @staticmethod
    def route_request(intent: str, payload: dict):
        intent = intent.lower()

        # 1. Multi-Project Generation Agent
        if 'project_gen_multiple' in intent or 'projects_gen' in intent:
            return generate_projects_ai(
                requirement=payload.get('requirement', ''),
                domain=payload.get('domain', ''),
                difficulty=payload.get('difficulty', 'Intermediate'),
                duration=payload.get('duration', '2 Weeks'),
                skills=payload.get('required_skills', ''),
                business_context=payload.get('business_context', ''),
                count=payload.get('count', 5)
            )

        # 1b. Single Project Generation Agent
        elif 'project_gen' in intent or 'create_project' in intent:
            return generate_project_ai(
                requirement=payload.get('requirement', ''),
                domain=payload.get('domain', ''),
                difficulty=payload.get('difficulty', 'Intermediate'),
                duration=payload.get('duration', '2 Weeks'),
                skills=payload.get('required_skills', ''),
                business_context=payload.get('business_context', '')
            )

        # 2. Technology Recommendation Agent
        elif 'tech_rec' in intent:
            return recommend_technologies_ai(payload.get('project_data', {}))

        # 3. Real-World Scenario Agent
        elif 'scenario' in intent:
            return generate_scenario_ai(payload.get('project_data', {}))

        # 4. Intern Matching Agent
        elif 'matching' in intent:
            return match_interns_ai(
                project_data=payload.get('project_data', {}),
                interns_list=payload.get('interns_list', [])
            )

        # 5. Dedicated Project Progress & Velocity Tracking Agent
        elif 'tracking' in intent or 'progress' in intent or 'velocity' in intent:
            return track_project_progress_ai(
                assignment_info=payload.get('assignment_info', {}),
                tasks_list=payload.get('tasks_list', [])
            )

        # 6. Dedicated Project Health Diagnostic & Scoring Agent
        elif 'health' in intent or 'audit' in intent or 'score' in intent:
            return analyze_project_health_ai(
                assignment_info=payload.get('assignment_info', {}),
                tasks_list=payload.get('tasks_list', []),
                submission_info=payload.get('submission_info')
            )

        # 6. Submission Evaluation Agent (with RAG Context)
        elif 'evaluation' in intent:
            submission_text = payload.get('submission_text', '')
            sample_text = payload.get('sample_text', '')
            criteria = payload.get('criteria', '')
            expected_sections = payload.get('expected_sections', '')

            # RAG semantic context injection
            rag_context = run_rag_pipeline(query=criteria, reference_texts=[sample_text] if sample_text else [])
            augmented_sample = f"{sample_text}\n\n[RAG Retrieved Focus Areas]:\n{rag_context}" if rag_context else sample_text

            return evaluate_submission_ai(
                submission_text=submission_text,
                sample_text=augmented_sample,
                criteria=criteria,
                expected_sections=expected_sections
            )

        # 7. Feedback Agent
        elif 'feedback' in intent:
            return generate_feedback_ai(payload.get('evaluation_data', {}))

        # 8. Copilot Agent
        elif 'copilot' in intent:
            question = payload.get('question', '')
            system_context = payload.get('system_context', {})
            return copilot_response_ai(question, system_context)

        # 9. Document Structure & Format Verification Agent
        elif 'doc' in intent or 'structure' in intent or 'format' in intent:
            return validate_document_structure_ai(
                document_text=payload.get('document_text', ''),
                filename=payload.get('filename', 'document.txt'),
                doc_category=payload.get('category', 'Technical Specification')
            )

        return {"status": "Unknown intent", "intent": intent}
