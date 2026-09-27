from gemini_service import generate_project_ai

def test_chai_generation():
    print("Testing generate_project_ai with Chai requirement...")
    prompt = "i need advanced multi agents project related to chai business"
    result = generate_project_ai(prompt, "Artificial Intelligence / NLP", "Advanced", "8 Weeks")
    
    print("Generated Title:", result.get('title'))
    print("Domain:", result.get('domain'))
    print("Problem Statement Length:", len(result.get('problem_statement', '')))
    print("Abstract Length:", len(result.get('abstract', '')))
    print("Required Skills:", result.get('required_skills'))
    print("Technologies:", result.get('technologies'))
    
    assert "ChaiChain" in result.get('title') or "Demand" in result.get('title') or "Agent" in result.get('title')
    assert len(result.get('problem_statement', '')) > 50
    assert len(result.get('abstract', '')) > 50
    assert "Python" in result.get('required_skills') or "LangGraph" in result.get('required_skills')
    
    print("\nCHAI PROJECT GENERATION TEST PASSED!")

if __name__ == '__main__':
    test_chai_generation()
