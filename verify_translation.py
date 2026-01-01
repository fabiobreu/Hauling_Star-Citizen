import hauling_web_tst
import re

# Mock flask context
with hauling_web_tst.app.test_request_context():
    html = hauling_web_tst.index()
    
    # Check for Portuguese words
    pt_words = [
        "Missão", "Aceita", "Entregue", "Coletar", "Pegar", "Lendo", 
        "histórico", "PAUSAR", "RETOMAR", "NOVOS CONTRATOS", "adicionar itens"
    ]
    
    found_pt = []
    for word in pt_words:
        if word.lower() in html.lower():
            found_pt.append(word)
            
    if found_pt:
        print(f"FAILED: Found Portuguese words in HTML: {found_pt}")
    else:
        print("SUCCESS: No Portuguese words found in HTML.")

    # Check source code for Portuguese regex keywords
    with open("hauling_web_tst.py", "r", encoding="utf-8") as f:
        content = f.read()
        
    pt_regex = ["Entregue", "Coletar", "Pegar"]
    found_regex = []
    for word in pt_regex:
        # Simple check, might have false positives if these words exist in English (unlikely for these)
        if word in content:
            found_regex.append(word)
            
    if found_regex:
        print(f"WARNING: Found Portuguese words in source code (might be regex): {found_regex}")
    else:
        print("SUCCESS: No Portuguese regex keywords found in source code.")
