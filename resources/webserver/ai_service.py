import os
import openai
import json
import logging
from typing import Any, Dict
from pydantic import BaseModel
from webserver.tools.toxicity_models_simple import ChemicalToxicityAssessment

logger = logging.getLogger(__name__)

openai.api_key = os.environ.get('OPENAI_API_KEY')

def capitalize_words(s: str) -> str:
    return ' '.join(word.capitalize() for word in s.split())

def generate_title(message: str) -> str:
    """Generate a short title summarizing the given message using OpenAI."""
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Provide a short title summarizing the user's request. The title should be no more than 10 words."},
                {"role": "user", "content": message},
            ],
            max_tokens=10,
            temperature=0.5,
        )
        title = resp.choices[0].message["content"].strip()
        return capitalize_words(title)
    except Exception:
        return capitalize_words(message.strip())

def convert_pydantic_to_markdown(model_data: Dict[str, Any], original_query: str = "") -> str:
    """
    Convert a Pydantic model (as dict) to a comprehensive markdown report using Gemini 2.5 Flash.
    
    Args:
        model_data: The Pydantic model data as a dictionary
        original_query: The original user query for context
        
    Returns:
        str: A comprehensive markdown report
    """
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        # Initialize Gemini model
        gemini_model = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.environ.get("GEMINI_API_KEY")
        )
        
        # Convert Pydantic model to dict if it's not already a dict
        if hasattr(model_data, 'model_dump'):
            # It's a Pydantic model, convert to dict
            serializable_data = model_data.model_dump()
        elif hasattr(model_data, 'dict'):
            # It's a Pydantic model (older version), convert to dict
            serializable_data = model_data.dict()
        else:
            # It's already a dict or other serializable type
            serializable_data = model_data
        
        # Ensure all nested objects are serializable by converting to JSON and back
        # This handles cases where the dict contains Pydantic models or other non-serializable objects
        try:
            # Test serialization and deserialization to ensure everything is JSON serializable
            json_str = json.dumps(serializable_data, default=str, ensure_ascii=False)
            serializable_data = json.loads(json_str)
        except Exception as e:
            logger.warning(f"Failed to ensure JSON serialization: {e}")
            # If serialization fails, try to convert any remaining Pydantic objects
            def convert_pydantic_objects(obj):
                if hasattr(obj, 'model_dump'):
                    return obj.model_dump()
                elif hasattr(obj, 'dict'):
                    return obj.dict()
                elif isinstance(obj, dict):
                    return {k: convert_pydantic_objects(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_pydantic_objects(item) for item in obj]
                else:
                    return str(obj)
            
            serializable_data = convert_pydantic_objects(serializable_data)
        
        # Create a comprehensive prompt for conversion
        prompt = f"""
        You are an expert scientific writer tasked with converting structured toxicity assessment data into a comprehensive, well-formatted markdown report.
        
        Original Query: {original_query}
        
        Structured Data:
        {json.dumps(serializable_data, indent=2, ensure_ascii=False)}
        
        Please convert this structured data into a comprehensive markdown report with the following structure:
        
        # Chemical Toxicity Assessment Report
        
        ## Executive Summary
        [Brief overview of the assessment]
        
        ## Chemical Properties Analysis
        [Detailed analysis of chemical properties and their relevance to toxicity]
        
        ## Toxicity Mechanisms
        [Comprehensive analysis of toxicity mechanisms with supporting evidence]
        
        ## Clinical Evidence
        [Detailed review of clinical studies, case reports, and treatment protocols]
        
        ## Risk Assessment
        [Statistical analysis including risk distribution, confidence intervals, and population analysis]
        
        ## Risk Factors and Populations
        [Analysis of high-risk groups, modifying factors, and preventive measures]
        
        ## References
        [Comprehensive list of all references used in the analysis]
        
        Requirements:
        1. Use clear, scientific language appropriate for toxicology professionals
        2. Include all relevant data from the structured input
        3. Format statistical data with proper confidence intervals
        4. Ensure all claims are properly referenced
        5. Use appropriate markdown formatting (headers, lists, tables, emphasis)
        6. Make the report comprehensive but readable
        7. Include specific data points and statistical analysis where available
        8. Maintain scientific rigor while being accessible
        
        The report should be comprehensive, well-structured, and suitable for toxicology professionals.
        """
        
        # Generate the markdown report
        response = gemini_model.invoke(prompt)
        return response.content
        
    except Exception as e:
        # Fallback: create a basic markdown report
        try:
            # Try to convert to dict for the fallback as well
            if hasattr(model_data, 'model_dump'):
                serializable_data = model_data.model_dump()
            elif hasattr(model_data, 'dict'):
                serializable_data = model_data.dict()
            else:
                serializable_data = model_data
            
            # Ensure serialization works in fallback too
            try:
                json_str = json.dumps(serializable_data, default=str, ensure_ascii=False)
                serializable_data = json.loads(json_str)
            except Exception:
                # If serialization fails, convert any remaining Pydantic objects
                def convert_pydantic_objects(obj):
                    if hasattr(obj, 'model_dump'):
                        return obj.model_dump()
                    elif hasattr(obj, 'dict'):
                        return obj.dict()
                    elif isinstance(obj, dict):
                        return {k: convert_pydantic_objects(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_pydantic_objects(item) for item in obj]
                    else:
                        return str(obj)
                
                serializable_data = convert_pydantic_objects(serializable_data)
                
            return f"""
            # Chemical Toxicity Assessment Report

            ## Error in Conversion
            The structured data could not be converted to markdown due to an error: {str(e)}

            ## Original Query
            {original_query}

            ## Structured Data
            ```json
            {json.dumps(serializable_data, indent=2, ensure_ascii=False)}
            ```
            """
        except Exception as fallback_error:
            return f"""
            # Chemical Toxicity Assessment Report

            ## Error in Conversion
            The structured data could not be converted to markdown due to an error: {str(e)}
            Additional error in fallback: {str(fallback_error)}

            ## Original Query
            {original_query}

            ## Structured Data
            Unable to serialize the data structure.
            """

