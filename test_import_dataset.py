import io
import json
from app import app
from database import get_db

def test_dataset_import_flows():
    client = app.test_client()
    
    # 1. Authenticate / Login as Mentor
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'mentor'
        sess['full_name'] = 'Dr. Mentor'
        sess['email'] = 'mentor@smartbridge.com'

    print("[TEST 1] Testing CSV Dataset Ingestion into Projects Database...")
    sample_csv = """title,problem_statement,abstract,technologies,domain,difficulty,duration,required_skills
"Autonomous Logistics Dynamic Dispatcher","Freight routes suffer from real-time dynamic congestion and warehouse bottlenecks.","A reinforcement-learning multi-agent engine that optimizes multi-stop freight route allocation.","Python, LangGraph, OR-Tools, FastAPI, Redis, Docker","Artificial Intelligence / NLP","Advanced","6 Weeks","Python, FastAPI, Redis, Docker"
"Clinical Prescription OCR Validator","Illegible handwritten prescription notes cause pharmaceutical dispensing errors.","A Vision Transformer and TrOCR pipeline that extracts structured medicine dosage tables from photos.","Python, TrOCR, PyTorch, OpenCV, Gemini API, Streamlit","Healthcare","Intermediate","4 Weeks","Python, PyTorch, Computer Vision, OpenCV"
"""
    csv_data = {
        'dataset_file': (io.BytesIO(sample_csv.encode('utf-8')), 'test_projects.csv'),
        'target': 'list'
    }
    
    resp = client.post('/projects/import', data=csv_data, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    assert b"Successfully imported" in resp.data or b"Autonomous Logistics" in resp.data
    print(" -> CSV Dataset import to database passed!")

    print("[TEST 2] Testing JSON Dataset Ingestion into Projects Database...")
    sample_json = json.dumps([
        {
            "title": "Quantum Key Distribution Network Simulator",
            "problem_statement": "Post-quantum cryptographic transitions need robust simulation of photon loss and decoy state protocols.",
            "abstract": "A Python quantum network simulation benchmark comparing BB84 and E91 protocols under noisy fiber conditions.",
            "technologies": "Python, Qiskit, SimulaQron, NumPy, Matplotlib, Docker",
            "required_skills": "Python, Quantum Computing, Linear Algebra, Docker",
            "domain": "Cybersecurity",
            "difficulty": "Expert",
            "duration": "8 Weeks"
        }
    ])
    
    json_data = {
        'dataset_file': (io.BytesIO(sample_json.encode('utf-8')), 'quantum_projects.json'),
        'target': 'list'
    }
    resp2 = client.post('/projects/import', data=json_data, content_type='multipart/form-data', follow_redirects=True)
    assert resp2.status_code == 200
    assert b"Successfully imported" in resp2.data or b"Quantum Key Distribution" in resp2.data
    print(" -> JSON Dataset import to database passed!")

    print("[TEST 3] Testing Dataset Ingestion into AI Project Creator (target=create)...")
    single_csv = """title,problem_statement,abstract,technologies,required_skills
"Smart Urban Flood Warning System","Municipal storm drain sensors lack automated predictive anomaly detection during flash floods.","An IoT time-series forecasting service predicting urban water levels 2 hours before road flooding occurs.","Python, Prophet, FastAPI, TimescaleDB, Grafana, Docker","Python, Time Series, FastAPI, Docker"
"""
    create_data = {
        'dataset_file': (io.BytesIO(single_csv.encode('utf-8')), 'flood_project.csv')
    }
    resp3 = client.post('/projects/import?target=create', data=create_data, content_type='multipart/form-data', follow_redirects=True)
    assert resp3.status_code == 200
    assert b"Smart Urban Flood Warning System" in resp3.data
    assert b"Municipal storm drain sensors" in resp3.data
    assert b"Smart Urban Flood Warning System" in resp3.data
    print(" -> Import into AI Project Creator passed!")

    print("[TEST 4] Verifying Projects Table in Database contains imported entries...")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, technologies, problem_statement, abstract, required_skills FROM projects WHERE title LIKE '%Quantum Key Distribution%' OR title LIKE '%Autonomous Logistics%'")
    rows = cursor.fetchall()
    conn.close()
    
    assert len(rows) >= 2
    for r in rows:
        print(f"   [DB Verified] Title: {r['title']} | Tools: {r['technologies']} | Abstract: {r['abstract'][:40]}...")
    
    print("\nALL DATASET IMPORT TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    test_dataset_import_flows()
