import urllib.request
from app import app, init_db, seed_db

def test_intern_signup_complete():
    init_db()
    seed_db()
    
    # 1. Test Static & HTML URLs
    urls = [
        'http://127.0.0.1:5000/intern/signup',
        'http://127.0.0.1:5000/static/style.css',
        'http://127.0.0.1:5000/static/css/style.css',
        'http://127.0.0.1:5000/static/images/intern-mentor-3d.png',
        'http://127.0.0.1:5000/static/img/intern-mentor-3d.png'
    ]

    for url in urls:
        req = urllib.request.urlopen(url)
        print(f'{url} -> status {req.getcode()}, length {len(req.read())}')

    # 2. Test Content
    client = app.test_client()
    res = client.get('/intern/signup')
    assert res.status_code == 200
    data = res.data.decode('utf-8')

    checklist = [
        'Start Your',
        'Internship Journey',
        'Learn. Build. Improve. Grow.',
        'My Projects',
        'My Tasks',
        'Track Progress',
        'AI Feedback',
        'intern-mentor-3d.png',
        'Learn.<br>Build.<br>Grow.<br>Together.',
        'Create Your Intern Account',
        'Full Name',
        'Email',
        'Password',
        'Confirm Password',
        'College / University',
        'Course & Major',
        'Skills & Domain',
        'Technologies Known',
        'Project Experience / Year of Study',
        'Create Intern Account',
        'Already have an account?',
        'Sign In',
        'Are you a mentor?',
        'Join as Mentor',
        '© 2026 Mentora AI'
    ]

    for item in checklist:
        assert item in data, f'MISSING: {item}'
        print(f'[PASS] Found: {item}')

    forbidden = [
        'Quick Demo Credentials',
        'Better Projects. Brighter Futures.',
        'Mentor demo account',
        'Intern demo account',
        '1-Click Login'
    ]

    for item in forbidden:
        assert item not in data, f'FORBIDDEN FOUND: {item}'
        print(f'[PASS] Verified absent: {item}')

    # 3. Validation test (Password Mismatch)
    res_mismatch = client.post('/intern/signup', data={
        'full_name': 'Alex Rivera Test',
        'email': 'alex.test.mismatch@university.edu',
        'password': 'password123',
        'confirm_password': 'password456',
        'college': 'NIT',
        'course': 'B.S. CS',
        'skills': 'Python, NLP',
        'technologies': 'Flask, PyTorch',
        'experience': '3rd Year • Built NLP Chatbot'
    }, follow_redirects=True)
    assert res_mismatch.status_code == 200
    assert 'Passwords do not match' in res_mismatch.data.decode('utf-8')
    print('[PASS] Password mismatch validation flashed properly')

    # 4. Successful registration test
    res_success = client.post('/intern/signup', data={
        'full_name': 'Alex Rivera',
        'email': 'alex.rivera.fresh@university.edu',
        'password': 'password123',
        'confirm_password': 'password123',
        'college': 'National Institute of Technology',
        'course': 'B.S. Computer Science',
        'skills': 'Python, NLP, Prompt Engineering',
        'technologies': 'Python, Flask, PyTorch, SQL',
        'experience': '3rd Year • Built NLP Chatbot'
    }, follow_redirects=False)
    assert res_success.status_code == 302
    print(f'[PASS] Successful registration redirects to {res_success.headers["Location"]}')
    print('ALL INTERN SIGNUP VERIFICATIONS PASSED!')

if __name__ == '__main__':
    test_intern_signup_complete()
