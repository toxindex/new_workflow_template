import sys
import json
from pathlib import Path

# Add parent directory to path to allow importing build_KE modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from build_KE_nocache import process_single_pdf
from generate_report import generate_report

# PDF is in the same directory as this test file
input_file = Path(__file__).parent / '32439582.pdf'
topic = 'endocrine disruption'

# Cache file for result_dict (in the same directory as this test file)
result_dict_cache = Path(__file__).parent / 'result_dict_cache.json'

# Load cached result_dict if it exists, otherwise process PDF
if result_dict_cache.exists():
    print(f"Loading cached result_dict from {result_dict_cache}...")
    with open(result_dict_cache, 'r', encoding='utf-8') as f:
        result_dict = json.load(f)
    print("✓ Loaded cached result_dict")
else:
    print(f"Processing PDF: {input_file}")
    print("This may take several minutes...")
    result_dict = process_single_pdf(input_file, topic)
    
    # Check for errors
    if 'error' in result_dict:
        raise ValueError(f"Error processing PDF: {result_dict.get('error', 'Unknown error')} - {result_dict.get('message', '')}")
    
    # Save result_dict for future use
    print(f"Saving result_dict to {result_dict_cache}...")
    with open(result_dict_cache, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)
    print("✓ Saved result_dict for future use")

# Generate report
print(f"\nGenerating report for topic: {topic}")
report = generate_report(result_dict, topic)

# Save report to file (in the same directory as this test file)
report_filename = Path(__file__).parent / 'test_report.md'
with open(report_filename, 'w', encoding='utf-8') as f:
    f.write(report)
print(f"\n✓ Report saved to: {report_filename}")

