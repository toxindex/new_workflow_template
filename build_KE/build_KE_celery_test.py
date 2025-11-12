import os
import sys
import tempfile
import pandas as pd
from pathlib import Path

# Load environment variables from .env file
import dotenv
dotenv.load_dotenv()

# Add parent directory to path to allow importing webserver module
sys.path.insert(0, str(Path(__file__).parent.parent))

from build_KE_nocache import process_single_pdf, create_llm
from webserver.storage import GCSFileStorage

def extract_topic_from_query(user_query: str) -> str:
    """Extract the topic from user query. Returns just the topic name, e.g., 'endocrine disruption'."""
    llm = create_llm()
    prompt = f"""Extract only the topic name from the following query. Return ONLY the topic name, nothing else, no explanation.

Query: {user_query}

Topic:"""
    response = llm.invoke(prompt)
    topic = response.content if hasattr(response, 'content') else str(response)
    # Clean up the response - take only the first line and strip whitespace
    topic = topic.strip().split('\n')[0].strip()
    # Remove quotes if present
    topic = topic.strip('"').strip("'")
    return topic

def build_KE():
    print("=" * 60)
    print("Starting build_KE test")
    print("=" * 60)
    
    user_query = 'Extract Key Events from the following PDF: 32439582.pdf on topic: "endocrine disruption"'
    input_file = Path('32439582.pdf')
    
    print(f"\n[1/5] Extracting topic from user query...")
    print(f"      Query: {user_query}")
    topic = extract_topic_from_query(user_query)
    print(f"      ✓ Topic extracted: {topic}")
    
    print(f"\n[2/5] Processing PDF: {input_file}")
    print(f"      This may take several minutes...")
    result_dict = process_single_pdf(input_file, topic)
    
    # Check for errors in result
    if 'error' in result_dict:
        raise ValueError(f"Error processing PDF: {result_dict.get('error', 'Unknown error')} - {result_dict.get('message', '')}")
    
    print(f"      ✓ PDF processed successfully")
    print(f"      - Key events: {len(result_dict.get('key_events', []))}")
    print(f"      - Relationships: {len(result_dict.get('relationships', []))}")
    print(f"      - Evidence records: {len(result_dict.get('evidence', []))}")

    KE_filename = f"KE_{input_file.stem}.csv"
    Relationships_filename = f"Relationships_{input_file.stem}.csv"
    Evidence_filename = f"Evidence_{input_file.stem}.csv"
    
    # Convert lists to DataFrames and write to CSV
    temp_ke_csv_path = None
    temp_relationships_csv_path = None
    temp_evidence_csv_path = None
    
    try:
        print(f"\n[3/5] Creating CSV files...")
        
        # Create temporary files and write CSV data
        print(f"      Creating {KE_filename}...")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_ke_csv_file:
            temp_ke_csv_path = temp_ke_csv_file.name
            df_ke = pd.DataFrame(result_dict['key_events'])
            df_ke.to_csv(temp_ke_csv_path, index=False)
        print(f"      ✓ {KE_filename} created ({len(df_ke)} rows)")
        
        print(f"      Creating {Relationships_filename}...")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_relationships_csv_file:
            temp_relationships_csv_path = temp_relationships_csv_file.name
            df_relationships = pd.DataFrame(result_dict['relationships'])
            df_relationships.to_csv(temp_relationships_csv_path, index=False)
        print(f"      ✓ {Relationships_filename} created ({len(df_relationships)} rows)")
        
        print(f"      Creating {Evidence_filename}...")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_evidence_csv_file:
            temp_evidence_csv_path = temp_evidence_csv_file.name
            df_evidence = pd.DataFrame(result_dict['evidence'])
            df_evidence.to_csv(temp_evidence_csv_path, index=False)
        print(f"      ✓ {Evidence_filename} created ({len(df_evidence)} rows)")
        
        # Upload to GCS
        print(f"\n[4/5] Uploading files to GCS...")
        gcs_storage = GCSFileStorage()  
        task_id = 'testing_build_KE_celery'
        
        # Upload csv file
        print(f"      Uploading {KE_filename}...")
        KE_gcs_path = f"tasks/{task_id}/{KE_filename}"
        gcs_storage.upload_file(temp_ke_csv_path, KE_gcs_path, content_type='text/csv')
        print(f"      ✓ Uploaded to: {KE_gcs_path}")
        
        print(f"      Uploading {Relationships_filename}...")
        Relationships_gcs_path = f"tasks/{task_id}/{Relationships_filename}"
        gcs_storage.upload_file(temp_relationships_csv_path, Relationships_gcs_path, content_type='text/csv')
        print(f"      ✓ Uploaded to: {Relationships_gcs_path}")
        
        print(f"      Uploading {Evidence_filename}...")
        Evidence_gcs_path = f"tasks/{task_id}/{Evidence_filename}"
        gcs_storage.upload_file(temp_evidence_csv_path, Evidence_gcs_path, content_type='text/csv')
        print(f"      ✓ Uploaded to: {Evidence_gcs_path}")
    finally:
        # Clean up temporary files
        print(f"\n[5/5] Cleaning up temporary files...")
        if temp_ke_csv_path and os.path.exists(temp_ke_csv_path):
            os.unlink(temp_ke_csv_path)
            print(f"      ✓ Removed {temp_ke_csv_path}")
        if temp_relationships_csv_path and os.path.exists(temp_relationships_csv_path):
            os.unlink(temp_relationships_csv_path)
            print(f"      ✓ Removed {temp_relationships_csv_path}")
        if temp_evidence_csv_path and os.path.exists(temp_evidence_csv_path):
            os.unlink(temp_evidence_csv_path)
            print(f"      ✓ Removed {temp_evidence_csv_path}")
    
    print("\n" + "=" * 60)
    print("✓ Test completed successfully!")
    print("=" * 60)
    return 


if __name__ == "__main__":
    build_KE()
