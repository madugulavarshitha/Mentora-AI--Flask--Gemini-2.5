import io
from app import app
from database import init_db, seed_db

def test_full_suite():
    init_db()
    seed_db()
    client = app.test_client()

    print("\n--- 1. Testing Landing Page & Dedicated Auth Routes ---")
    res = client.get('/')
    assert res.status_code == 200
    assert b"Smarter Mentorship" in res.data
    assert b"Join as Mentor" in res.data
    assert b"Join as Intern" in res.data
    print("[PASS] Landing page (/) verified")

    res = client.get('/mentor/signin')
    assert res.status_code == 200
    assert b"Sign in to your mentor workspace" in res.data
    print("[PASS] Mentor Sign In page verified")

    res = client.get('/mentor/signup')
    assert res.status_code == 200
    assert b"Create Your Mentor" in res.data
    print("[PASS] Mentor Sign Up page verified")

    res = client.get('/intern/signin')
    assert res.status_code == 200
    assert b"Sign in to your intern workspace" in res.data
    print("[PASS] Intern Sign In page verified")

    res = client.get('/intern/signup')
    assert res.status_code == 200
    assert b"Internship Journey" in res.data
    print("[PASS] Intern Sign Up page verified")

    print("\n--- 2. Testing Mentor & Intern Authentication ---")
    # Mentor Login
    res = client.post('/mentor/signin', data={'identifier': 'varshitha@gmail.com', 'password': 'varshitha123'}, follow_redirects=True)
    assert b"Good morning" in res.data or b"Mentor" in res.data
    print("[PASS] Mentor Sign In flow verified")

    # Intern Login
    client.get('/logout', follow_redirects=True)
    res = client.post('/intern/signin', data={'identifier': 'bhumika@gmail.com', 'password': 'bhumika123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Intern Dashboard" in res.data or b"Workspace" in res.data
    print("[PASS] Intern Sign In flow verified")

    print("\n--- 3. Testing Project AI Generation & Details ---")
    client.get('/quick-switch/2', follow_redirects=True) # Switch to mentor
    res = client.post('/projects/generate', data={
        'requirement': 'Develop a real-time smart traffic anomaly detector using computer vision',
        'domain': 'Computer Vision & Deep Learning',
        'difficulty': 'Intermediate',
        'duration': '8 Weeks',
        'required_skills': 'Python, OpenCV, PyTorch',
        'business_context': 'Smart City transportation hub'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Review, Edit & Save Project" in res.data
    print("[PASS] Project AI generation succeeded")

    print("\n--- 4. Testing Tech Recommendations & Real-World Scenario ---")
    res = client.get('/projects/1/tech-recommendations')
    assert res.status_code == 200
    assert b"AI Technology Stack Recommendations" in res.data
    print("[PASS] Tech recommendations page loaded")

    res = client.get('/projects/1/scenario')
    assert res.status_code == 200
    assert b"Enterprise Real-World Scenario Generation" in res.data
    print("[PASS] Real-world scenario page loaded")

    print("\n--- 5. Testing Intern Matching Engine ---")
    res = client.get('/matching?project_id=1')
    assert res.status_code == 200
    assert b"AI Evaluated & Ranked Intern Candidates" in res.data
    assert b"Match Score" in res.data
    print("[PASS] Intern matching engine verified")

    print("\n--- 6. Testing Project Tracking & Health Audit ---")
    res = client.get('/health')
    assert res.status_code == 200
    assert b"Project Tracking & Health Matrix" in res.data
    print("[PASS] Project tracking overview verified")

    res = client.get('/health/1')
    assert res.status_code == 200
    assert b"Gemini Health Diagnostic Report" in res.data
    print("[PASS] Project deep health audit verified")

    print("\n--- 7. Testing Document Upload & RAG Multi-Agent Evaluation ---")
    data = {
        'assignment_id': '1',
        'title': 'Test Python Docx Report',
        'notes': 'Unit test submission file',
        'submission_file': (io.BytesIO(b"# Sample Report Content\n1. Executive Summary\n2. System Architecture\n3. Implementation"), 'report.txt')
    }
    res = client.post('/submissions/submit-document', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert res.status_code == 200
    print("[PASS] Document submission verified")

    res = client.get('/evaluations/1')
    assert res.status_code == 200
    assert b"AI Evaluation Report" in res.data
    print("[PASS] AI Evaluation verified")

    res = client.get('/feedback/1')
    assert res.status_code == 200
    assert b"Actionable Mentorship Feedback Report" in res.data
    print("[PASS] AI Feedback report verified")

    print("\n--- 8. Testing Mentor AI Copilot ---")
    res = client.post('/copilot/ask', data={'question': 'Show delayed projects.'})
    assert res.status_code == 200
    assert b"AI Copilot Response" in res.data
    print("[PASS] AI Copilot response verified")

    print("\n==================================================")
    print("  ALL TESTS PASSED WITH 100% SUCCESS!             ")
    print("==================================================")

if __name__ == '__main__':
    test_full_suite()
