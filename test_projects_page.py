import app

def test_projects():
    client = app.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['username'] = 'mentor1'
        sess['role'] = 'mentor'
        sess['full_name'] = 'Dr. Sarah Jenkins'

    res = client.get('/projects')
    print("STATUS:", res.status_code)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    
    html = res.get_data(as_text=True)
    
    checks = [
        ("Hero Title", "Project Blueprints & Curricula" in html),
        ("Hero Subtitle", "Browse mentor-designed and Gemini-generated enterprise project challenges." in html),
        ("Hero Quote", "Ideas guide." in html and "Projects build." in html),
        ("3D Hero Image", "projects-hero-3d.png" in html),
        ("Stat 1 (Total Projects)", "Total Projects" in html and "8" in html),
        ("Stat 2 (Active Projects)", "Active Projects" in html and "6" in html),
        ("Stat 3 (Completed Projects)", "Completed Projects" in html and "2" in html),
        ("Stat 4 (AI Generated)", "AI Generated" in html and "4" in html),
        ("Table Title", "All Projects" in html),
        ("Table Tabs", "All Projects" in html and "Active" in html and "Completed" in html),
        ("Table Row 1 (Zoo Park)", "AI-Driven Data Science System for zoo park maintainance" in html),
        ("Table Row 2 (Customer Support)", "AI-Driven Customer Support Assistant" in html),
        ("Table Row 3 (Production Support)", "AI Production Customer Support System" in html),
        ("Table Row 4 (Chatbot Draft)", "AI Chatbot Assistant Draft" in html),
        ("Table Row 6 (Smart City Traffic)", "Smart City Vision Traffic Intelligence" in html),
        ("Table Row 7 (Smart Medical)", "Smart Medical Prescription" in html),
        ("Difficulty Badges", "Beginner" in html and "Intermediate" in html and "Advanced" in html),
        ("AI Suite Actions", "Tech Stack" in html and "Scenario" in html),
        ("View Details", "View Details" in html),
        ("Project Insights Card", "Project Insights" in html and "75%" in html),
        ("Quick Actions Card", "Quick Actions" in html and "Create New Project" in html and "Generate with AI" in html),
        ("3D Motive Banner", "projects-bottom-motive-3d.png" in html),
        ("CSS link", "style.css" in html)
    ]
    
    all_passed = True
    for name, passed in checks:
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] {name}")
        if not passed:
            all_passed = False
            
    if all_passed:
        print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
    else:
        print("\nSOME CHECKS FAILED.")

if __name__ == '__main__':
    test_projects()
