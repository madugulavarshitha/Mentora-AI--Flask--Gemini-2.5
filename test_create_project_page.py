from app import app

def test_create_project_page():
    client = app.test_client()
    
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'mentor'
        sess['full_name'] = 'Varshitha'
        sess['email'] = 'mentor@smartbridge.com'

    resp = client.get('/projects/create')
    print("STATUS:", resp.status_code)
    assert resp.status_code == 200

    html = resp.data.decode('utf-8')

    # Core checks matching the exact 3D Command Center
    checks = [
        ("Hero Title", "AI" in html and "Project Creator" in html),
        ("Hero Subtitle", "From Ideas to Impact" in html),
        ("Handwritten Tag", "Think" in html and "Enable Futures" in html),
        ("3D Right Stage Image", "ai-right-stage-3d.png" in html),
        ("Step 1 Title", "Describe Your Project Idea" in html),
        ("Requirement Field", 'id="requirement"' in html),
        ("Domain Field", 'id="domain"' in html),
        ("Difficulty Field", 'id="difficulty"' in html),
        ("Duration Field", 'id="duration"' in html),
        ("Generate Button", "Generate Multiple Projects with AI" in html or "Generate" in html),
        ("Upload Project Button", "Upload Project" in html),
        ("Upload Project Modal", "uploadProjectModal" in html),
        
        # Inspiration & Values
        ("Inspiration 1", "Multi-Agent Retail Ops" in html),
        ("Inspiration 2", "AWS Cloud GenAI Core" in html),
        ("Inspiration 3", "Hybrid Multi-Hop RAG" in html),
        ("Inspiration 4", "Deep Learning Vision" in html),
        ("Value Prop 1", "Multiple Blueprints" in html or "Save Time" in html),
        ("Value Prop 2", "Save or Delete" in html or "Better Projects" in html),
        ("Value Prop 3", "Intern Assignment" in html or "Empower Interns" in html),
        ("Value Prop 4", "Production Quality" in html or "Drive Impact" in html),
        ("Sidebar Active Item", "AI Project Creator" in html)
    ]

    all_passed = True
    for name, condition in checks:
        if condition:
            print(f"[PASS] {name}")
        else:
            print(f"[FAIL] {name}")
            all_passed = False

    assert all_passed, "Some checks failed!"
    print("\nALL CREATE PROJECT VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    test_create_project_page()
