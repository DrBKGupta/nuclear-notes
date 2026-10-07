import csv
import os
import sys

def search_question_bank(keyword):
    csv_file = "question_bank.csv"
    
    if not os.path.exists(csv_file):
        print(f"[-] Error: '{csv_file}' not found in the directory!")
        return

    print(f"\n[+] Searching 'question_bank.csv' for: '{keyword}'...\n" + "="*60)
    match_count = 0

    try:
        with open(csv_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, 1):
                # पूरी row के किसी भी कॉलम में की-वर्ड ढूंढना (Case-insensitive)
                row_string = " ".join(str(val) for val in row.values())
                if keyword.lower() in row_string.lower():
                    match_count += 1
                    print(f"Match #{match_count} (Row {row_num}):")
                    for header, value in row.items():
                        if value.strip():  # खाली फील्ड्स छोड़ दें
                            print(f"  {header.capitalize()}: {value}")
                    print("-" * 60)
                    
        print(f"[*] Search complete. Total matches found for '{keyword}': {match_count}\n")
        
    except Exception as e:
        print(f"[-] Error reading CSV file: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python csv_search.py <topic_or_keyword>")
        print("Example: python csv_search.py 'Appendicitis'")
    else:
        search_question_bank(sys.argv[1])