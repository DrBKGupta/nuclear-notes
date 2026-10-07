import csv
import random
import os

def run_active_recall_simulation():
    csv_file = "question_bank.csv" # मान लीजिए आपकी मुख्य CSV फाइल यह है
    
    if not os.path.exists(csv_file):
        print(f"[-] ORE ERROR: '{csv_file}' not found in the mine! Please check your raw data path.")
        return

    print("\n" + "="*60)
    print("☢️  NUCLEAR NOTES: ACTIVE RECALL SIMULATOR (RADIUM EXTRACTION) ☢️")
    print("="*60 + "\n")

    questions = []
    
    # CSV फाइल से कच्चा अयस्क (डेटा) पढ़ना
    try:
        with open(csv_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                questions.append(row)
    except Exception as e:
        print(f"[-] Error reading raw ore: {e}")
        return

    if not questions:
        print("[-] The mine is empty! No questions found in the CSV.")
        return

    # रैंडम क्लिनिकल केस निकालना (सिमुलेशन)
    case = random.choice(questions)
    
    print(f"[CASE SCENARIO / CLINICAL STEM]:\n{case.get('question', 'No question text found.')}\n")
    print("-" * 60)
    
    input("Press [Enter] to launch the Gold Standard Diagnosis & Explanation...")
    
    print("\n" + "="*60)
    print(f"💡 [GOLD STANDARD / CORRECT ANSWER]: {case.get('answer', 'N/A')}")
    print(f"📝 [HIGH-YIELD EXPLANATION]: {case.get('explanation', 'Review your core textbook capsule.')}")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_active_recall_simulation()