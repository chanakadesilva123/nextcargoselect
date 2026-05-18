import requests
import json
import time

API_URL = "http://localhost:8000/api/chat"

general_questions = [
    "Hello! How are you?",
    "What can you do?",
    "Can you help me pack items into boxes?",
    "What is the best way to pack fragile items?",
    "Do you know how to calculate the base area of a box?",
    "Who are you?",
    "Can you recommend a good packing strategy for a road trip?",
    "What is your purpose?",
    "Tell me a joke about packaging.",
    "Good morning!"
]

product_questions = [
    "Do you have any Yogurt?",
    "What is the price of BROOKLEA Real Fruit Yogurt?",
    "Do you sell Salsa?",
    "How much does Clasica Salsa cost?",
    "Is there any Hommus Dip available?",
    "I'm looking for Sweet Gold Potatoes, do you have them?",
    "What brand is the Hommus Dip?",
    "Tell me about the Slow Cooked Lamb Plated Meals.",
    "Do you have any Coles branded items?",
    "What is the price of Potatoes Sweet Gold?",
    "Do you carry products from Aldi?",
    "Can you give me a list of products under $5?",
    "Which products are good for a snack?",
    "Do you have any meals that are ready to eat?",
    "Are there any dairy products in stock?",
    "What is the cheapest item you have?",
    "Do you have items in the Vegetables category?",
    "Are there any fruit yogurts available?",
    "How big is the footprint of the products usually?",
    "Can you find me some dip for my chips?"
]

def test_questions(questions, category):
    print(f"\n--- Testing {category} Questions ---")
    results = []
    for i, q in enumerate(questions):
        print(f"Q{i+1}: {q}")
        try:
            resp = requests.post(API_URL, json={"query": q})
            if resp.status_code == 200:
                answer = resp.json().get("response", "")
                # print(f"A{i+1}: {answer}")
                print(f"A{i+1}: Success")
                results.append({"q": q, "a": answer, "status": "success"})
            else:
                print(f"Error {resp.status_code}: {resp.text}")
                results.append({"q": q, "a": resp.text, "status": "error"})
        except Exception as e:
            print(f"Exception: {e}")
            results.append({"q": q, "a": str(e), "status": "error"})
        time.sleep(1) # sleep briefly to avoid rate limiting
    return results

if __name__ == "__main__":
    g_results = test_questions(general_questions, "General")
    p_results = test_questions(product_questions, "Product")
    
    with open("chat_test_report.json", "w") as f:
        json.dump({"general": g_results, "product": p_results}, f, indent=2)
    
    print("\nTests complete. Results saved to chat_test_report.json")
