import pytest
from app import app
from gemini_service import generate_projects_ai

def test_generate_projects_ai():
    projects = generate_projects_ai(
        requirement="I need an autonomous supply chain agent for chai cafes",
        domain="Agentic AI",
        difficulty="Advanced",
        duration="2 Weeks",
        count=5
    )
    assert isinstance(projects, list)
    assert len(projects) >= 5
    for p in projects:
        assert 'title' in p and p['title']
        assert 'problem_statement' in p and p['problem_statement']
        assert 'abstract' in p and p['abstract']
        assert 'technologies' in p and p['technologies']
        assert 'domain' in p
        assert 'duration' in p
    print("[PASS] generate_projects_ai successfully generated 5 distinct blueprints in flashcards model!")

def test_creator_page_domains_and_durations():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'mentor'
        sess['full_name'] = 'Mentor'
        sess['email'] = 'mentor@smartbridge.com'

    resp = client.get('/projects/create')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')

    # Verify Domains
    expected_domains = [
        "Artificial Intelligence",
        "Gen AI",
        "Prompt Engineering",
        "Agentic AI",
        "Multi Agent",
        "RAG",
        "Machine Learning",
        "Deep Learning",
        "Computer Vision",
        "Vibe Coding",
        "IoT",
        "Robotics",
        "Cloud",
        "AWS",
        "Marketing"
    ]
    for d in expected_domains:
        assert f'<option value="{d}"' in html, f"Domain {d} missing from dropdown"

    # Verify Durations (1 Week, 2 Weeks, 3 Weeks, 4 Weeks)
    expected_durations = ["1 Week", "2 Weeks", "3 Weeks", "4 Weeks"]
    for dur in expected_durations:
        assert f'<option value="{dur}"' in html, f"Duration {dur} missing from dropdown"

    # Verify old durations are not present as options
    assert '<option value="6 Weeks"' not in html
    assert '<option value="8 Weeks"' not in html
    assert '<option value="12 Weeks"' not in html

    print("[PASS] Domains and Durations strictly verified!")

def test_multi_project_generation_and_saving():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'mentor'
        sess['full_name'] = 'Mentor'
        sess['email'] = 'mentor@smartbridge.com'

    # 1. Post to generate projects
    gen_resp = client.post('/projects/generate', data={
        'requirement': 'I need a RAG-based customer copilot for financial reports',
        'domain': 'RAG',
        'difficulty': 'Advanced',
        'duration': '3 Weeks',
        'business_context': 'Enterprise Banking'
    })
    assert gen_resp.status_code == 200
    gen_html = gen_resp.data.decode('utf-8')
    assert "Review Multiple Project Options" in gen_html
    assert "Project 1" in gen_html
    assert "Project 2" in gen_html
    assert "Project 3" in gen_html
    assert "Project 4" in gen_html
    assert "Project 5" in gen_html
    assert "Delete Option" in gen_html
    assert "Save Project" in gen_html

    # 2. Save one project via AJAX
    save_resp = client.post('/projects/save', data={
        'title': 'FinRAG Copilot: Enterprise Financial Intelligence Engine',
        'domain': 'RAG',
        'difficulty': 'Advanced',
        'duration': '3 Weeks',
        'business_context': 'Enterprise Banking',
        'requirement': 'I need a RAG-based customer copilot for financial reports',
        'problem_statement': 'Financial analysts spend excessive hours parsing 200-page quarterly reports manually.',
        'abstract': 'FinRAG Copilot integrates dense vector indexing with Gemini Flash and citation guardrails.',
        'technologies': 'Python, FastAPI, Qdrant, Gemini API, Docker',
        'action': 'save'
    }, headers={'X-Requested-With': 'XMLHttpRequest'})

    assert save_resp.status_code == 200
    save_json = save_resp.get_json()
    assert save_json['success'] is True
    project_id = save_json['project_id']
    assert project_id > 0

    # 3. View saved project showcase
    saved_view_resp = client.get(f'/projects/create?saved_id={project_id}')
    assert saved_view_resp.status_code == 200
    saved_html = saved_view_resp.data.decode('utf-8')
    assert "Project Saved to Repository!" in saved_html
    assert "FinRAG Copilot: Enterprise Financial Intelligence Engine" in saved_html
    assert "Problem Statement" in saved_html
    assert "FinRAG Copilot" in saved_html
    assert "savedProblemStatement" in saved_html
    assert "savedAbstract" in saved_html

    print("[PASS] Full generation, saving, and saved project showcase verified successfully!")

if __name__ == '__main__':
    test_generate_projects_ai()
    test_creator_page_domains_and_durations()
    test_multi_project_generation_and_saving()
    print("\nALL MULTI-PROJECT TESTS COMPLETED SUCCESSFULLY!")
