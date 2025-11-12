from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import re
import sys
import json
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import jsonschema
import yaml

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is not installed, continue without it

# LLM provider selection (default: openai)
llm_provider = os.environ.get("LLM_PROVIDER", "openai").lower()
print(f"Using LLM provider: {llm_provider}")

if llm_provider == "openai":
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4.1-nano-2025-04-14")
    summary_llm = ChatOpenAI(model="gpt-4.1-nano-2025-04-14")

    from agno.models.openai import OpenAIChat
    agent_model = OpenAIChat("gpt-4.1-2025-04-14")
else:
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    summary_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
 
    from agno.models.google import Gemini
    agent_model = Gemini(id="gemini-2.5-flash")

# Check for API key in environment
cse_api_key = os.environ.get("CSE_API_KEY")
google_cse_id = os.environ.get("GOOGLE_CSE_ID")

if not cse_api_key:
    print("\nError: Google API key not found!")
    print("Please set your Google API key using one of these methods:\n")
    print("1. Export as an environment variable:")
    print("   export CSE_API_KEY=your_google_api_key_here")
    print("\n2. Create a .env file in the project root with:")
    print("   CSE_API_KEY=your_google_api_key_here")
    print("\nYou can get an API key from: https://console.cloud.google.com/apis/credentials\n")
    sys.exit(1)

if not google_cse_id:
    print("\nError: Google CSE ID not found!")
    print("Please set your Google CSE ID using one of these methods:\n")
    print("1. Export as an environment variable:")
    print("   export GOOGLE_CSE_ID=your_cse_id_here")
    print("\n2. Create a .env file in the project root with:")
    print("   GOOGLE_CSE_ID=your_cse_id_here")
    print("\nYou can get a CSE ID from: https://cse.google.com/cse/all\n")
    sys.exit(1)

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_community import GoogleSearchAPIWrapper
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph
from agno.tools import tool
from agno.agent import Agent
from textwrap import dedent
from webserver.tools.chemprop import get_chemprop

# Import simplified models for OpenAI compatibility
from webserver.tools.toxicity_models_simple import (
    ChemicalToxicityAssessment,
    validate_reference_urls,
    Metadata,
    DataCompleteness,
    ChemicalProperties,
    ToxicityMechanisms,
    ClinicalEvidence,
    ToxicityRiskDistribution,
    RiskFactors,
    BetaDistributionParameters,
    ConfidenceInterval
)

class FormattedStreamHandler:
    def __init__(self):
        self.current_chunk = ""
        
    def __call__(self, chunk: Any) -> None:
        if isinstance(chunk, str):
            self.current_chunk += chunk
            if chunk.endswith("\n"):
                print(self.current_chunk, end="")
                self.current_chunk = ""
        else:
            print(json.dumps(chunk, indent=2))

search_tool = GoogleSearchAPIWrapper(google_api_key=cse_api_key, google_cse_id=google_cse_id)

# ── LCEL sub-chains ─────────────────────────────────────────────────────────────
query_generator_chain = (
    ChatPromptTemplate.from_template(
        """You are an expert at generating effective search queries.
        Given a user question, create a search query that will help find relevant information.

        User question: {question}

        Search query:"""
    )
    | llm
    | StrOutputParser()
)

summarizer_chain = (
    ChatPromptTemplate.from_template(
        """You are an expert at summarizing web content.
        Summarize the following search result in a concise but informative way:

        Title: {result[title]}
        Content: {result[content]}

        Summary:"""
    )
    | summary_llm
    | StrOutputParser()
)

follow_up_chain = (
    ChatPromptTemplate.from_template(
        """Based on the search results and their summaries, generate a follow-up question
        that would help gather more comprehensive information about the original query.

        Original query: {original_query}
        Search results: {search_results}
        Summaries: {summaries}

        Generate a specific follow-up question that explores an important aspect
        not fully covered in the current results:"""
    )
    | llm
    | StrOutputParser()
)

# ── helper functions (RunnableLambda wrappers) ──────────────────────────────────
def parse_search_results(search_text: str, top_k: int = 5) -> List[Dict[str, str]]:
    """Extract URLs, fetch their titles and a snippet of content."""
    print(f"Parsing search text (first 500 chars): {search_text[:500]}...")
    
    # Try to parse as JSON first (GoogleSearchAPIWrapper might return structured data)
    try:
        search_data = json.loads(search_text)
        print(f"Search data is JSON with keys: {list(search_data.keys()) if isinstance(search_data, dict) else 'not a dict'}")
        
        # Extract URLs from structured search results
        urls = []
        if isinstance(search_data, dict):
            # Look for items array or similar structure
            items = search_data.get('items', [])
            if not items and 'organic_results' in search_data:
                items = search_data.get('organic_results', [])
            
            for item in items[:top_k]:
                if isinstance(item, dict):
                    url = item.get('link') or item.get('url') or item.get('href')
                    if url:
                        urls.append(url)
    except json.JSONDecodeError:
        # Fallback to regex URL extraction
        urls = re.findall(r"https?://[^\s]+", search_text)[:top_k]
    
    print(f"Found {len(urls)} URLs: {urls}")
    
    parsed: List[Dict[str, str]] = []
    
    # If we found URLs, fetch their content
    if urls:
        for url in urls:
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    title = soup.title.string.strip() if soup.title and soup.title.string else url.split("//")[1].split("/")[0]
                    texts = soup.stripped_strings
                    content = " ".join(list(texts))[:1500]
                    if not content:
                        content = f"Content from {url}"
                else:
                    title = url.split("//")[1].split("/")[0]
                    content = f"Content from {url}"
            except Exception as e:
                print(f"Error fetching {url}: {e}")
                title = url.split("//")[1].split("/")[0]
                content = f"Content from {url}"
            parsed.append({
                "url": url,
                "title": title,
                "content": content,
            })
    else:
        # If no URLs found, create a summary from the search text itself
        print("No URLs found in search results, creating summary from search text")
        # Split the search text into chunks and create summaries
        text_chunks = [search_text[i:i+2000] for i in range(0, len(search_text), 2000)][:top_k]
        
        for i, chunk in enumerate(text_chunks):
            parsed.append({
                "url": f"search_result_{i+1}",
                "title": f"Search Result {i+1}",
                "content": chunk,
            })
    
    print(f"Parsed {len(parsed)} results")
    return parsed

def summarize_results(results: List[Dict[str, str]]) -> List[str]:
    summaries = []
    for i, r in enumerate(results):
        try:
            summary = summarizer_chain.invoke({"result": r})
            summaries.append(summary)
            print(f"Generated summary {i+1}/{len(results)}: {summary[:100]}...")
        except Exception as e:
            print(f"Error generating summary {i+1}: {e}")
            # Fallback: use a simple summary
            fallback_summary = f"Summary of {r.get('title', 'Unknown title')}: {r.get('content', 'No content available')[:200]}..."
            summaries.append(fallback_summary)
    return summaries

# Wrap helpers in RunnableLambda so they fit inside a graph
parse_results_runnable = RunnableLambda(parse_search_results)
summarize_results_runnable = RunnableLambda(summarize_results)

# ── graph state definition ──────────────────────────────────────────────────────
@dataclass
class SearchState:
    original_query: str

    # stage-by-stage fields (initially None and filled as the flow progresses)
    chemical_name: str | None = None
    toxicity_type: str | None = None
    search_query: str | None = None

    initial_search_results: str | None = None
    parsed_initial_results: List[Dict] | None = None
    initial_summaries: List[str] | None = None

    follow_up_query: str | None = None
    follow_up_search_results: str | None = None
    parsed_follow_up_results: List[Dict] | None = None
    follow_up_summaries: List[str] | None = None

    report: ChemicalToxicityAssessment | None = None

# ── node definitions ────────────────────────────────────────────────────────────
def _load_toxicity_types() -> List[str]:
    """Load toxicity types from YAML config with a safe fallback ordering."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "toxicity_types.yaml")
  
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        order = data.get("order")
        if isinstance(order, list) and order:
            return [str(x) for x in order]
        # Fall back to collecting from items if order not present
        items = data.get("items", [])
        names = [it.get("name") for it in items if isinstance(it, dict) and it.get("name")]
        if names:
            return [str(x) for x in names]
    return []

def preprocess_and_generate_query(state: SearchState) -> SearchState:
    """Extract chemical name and toxicity type, then format the query using both template and LLM-generated query."""
    # Extract chemical name
    chemical_messages = [
        ("system", "Given a prompt, extract the chemical name. Return only the chemical name."),
        ("human", state.original_query)
    ]
    chemical_name = llm.invoke(chemical_messages).content.strip()

    # Extract toxicity type with improved prompt
    toxicity_types = _load_toxicity_types()
    toxicity_types_str = ", ".join(toxicity_types)
    toxicity_messages = [
        ("system", f"""Given a toxicology query, extract the specific toxicity type being asked about. 
        Common toxicity types include: {toxicity_types_str}, etc.
        
        If the query asks "Is [chemical] [toxicity_type]?" or "Does [chemical] cause [toxicity_type]?", 
        extract the [toxicity_type] part.
        
        If the query doesn't specify a toxicity type, return "general toxicity".
        
        Return only the toxicity type."""),
        ("human", state.original_query)
    ]
    toxicity_type = llm.invoke(toxicity_messages).content.strip()

    # Format the expanded query (template)
    formatted_query = f"""Based on the following chemical properties of {chemical_name}:
    \nWhat are the {toxicity_type} effects and risks? Include:
    1. How these specific chemical properties may contribute to {toxicity_type}
    2. Known mechanisms of {toxicity_type} based on these properties
    3. Clinical evidence and case studies
    4. Beta distribution of the {chemical_name} having {toxicity_type} on a healthy individuals at regular dose and its probability with confidence interval.
    5. Risk factors and populations at risk
    """

    return SearchState(**{
        **asdict(state),
        "chemical_name": chemical_name,
        "toxicity_type": toxicity_type,
        "search_query": formatted_query
    })

def run_search(state: SearchState) -> SearchState:
    print(f"Running search for query: {state.search_query}")
    serp_text = search_tool.run(state.search_query)
    print(f"Search returned {len(serp_text)} characters")
    print(f"Search result type: {type(serp_text)}")
    return SearchState(**{**asdict(state), "initial_search_results": serp_text})

def parse_results(state: SearchState) -> SearchState:
    parsed = parse_search_results(state.initial_search_results)
    print(f"Parsed {len(parsed)} initial search results")
    for i, result in enumerate(parsed):
        print(f"Result {i+1}: {result.get('title', 'No title')[:50]}...")
    return SearchState(**{**asdict(state), "parsed_initial_results": parsed})

def summarize_initial(state: SearchState) -> SearchState:
    summaries = summarize_results(state.parsed_initial_results)
    return SearchState(**{**asdict(state), "initial_summaries": summaries})

def generate_follow_up(state: SearchState) -> SearchState:
    fq = follow_up_chain.invoke(
        {
            "original_query": state.original_query,
            "search_results": state.initial_search_results,
            "summaries": state.initial_summaries,
        }
    )
    return SearchState(**{**asdict(state), "follow_up_query": fq})

def run_follow_up_search(state: SearchState) -> SearchState:
    print(f"Running follow-up search for query: {state.follow_up_query}")
    serp_text = search_tool.run(state.follow_up_query)
    print(f"Follow-up search returned {len(serp_text)} characters")
    return SearchState(**{**asdict(state), "follow_up_search_results": serp_text})

def parse_follow_up(state: SearchState) -> SearchState:
    parsed = parse_search_results(state.follow_up_search_results)
    print(f"Parsed {len(parsed)} follow-up search results")
    for i, result in enumerate(parsed):
        print(f"Follow-up Result {i+1}: {result.get('title', 'No title')[:50]}...")
    return SearchState(**{**asdict(state), "parsed_follow_up_results": parsed})

def summarize_follow_up(state: SearchState) -> SearchState:
    summaries = summarize_results(state.parsed_follow_up_results)
    return SearchState(**{**asdict(state), "follow_up_summaries": summaries})

def generate_report(state: SearchState) -> SearchState:
    # Combine all parsed results for reference enforcement
    all_results = (state.parsed_initial_results or []) + (state.parsed_follow_up_results or [])
    
    # Extract and format references from search results
    references_text = ""
    if all_results:
        references_text = "\nAvailable References:\n"
        for i, result in enumerate(all_results):
            title = result.get('title', f'Reference {i+1}')
            url = result.get('url', '')
            content_preview = result.get('content', '')[:200] + "..." if len(result.get('content', '')) > 200 else result.get('content', '')
            references_text += f"{i+1}. {title}\n   URL: {url}\n   Content: {content_preview}\n\n"
    
    # Create a comprehensive prompt for the agent
    prompt = f"""
    Create a comprehensive toxicity assessment for the following query:
    
    Original Query: {state.original_query}
    Chemical Name: {state.chemical_name}
    Toxicity Type: {state.toxicity_type}
    
    Search Results:
    Initial Search: {state.initial_search_results}
    Initial Summaries: {state.initial_summaries}
    
    Follow-up Search: {state.follow_up_search_results}
    Follow-up Summaries: {state.follow_up_summaries}
    
    {references_text}
    
    IMPORTANT: You MUST include references in your response. Use the available references above to create proper citations.
    For each reference you use, include it in the references field with:
    - title: The title of the source
    - authors: If available from the content
    - year: If available from the content
    - url: The URL if available
    - type: "scientific_article", "review", "case_study", etc.
    - relevance: Brief description of how this reference supports your assessment
    
    Please create a comprehensive toxicity assessment using the Pydantic model structure.
    Ensure all data is properly referenced and scientifically rigorous.
    """
    
    # Use the agent to generate the report
    response = deeptox_agent.run(prompt)
    
    # Parse the response into the Pydantic model
    try:
        if isinstance(response.content, dict):
            report = ChemicalToxicityAssessment(**response.content)
        else:
            # If it's a string, try to parse it as JSON
            report_data = json.loads(response.content)
            report = ChemicalToxicityAssessment(**report_data)
    except Exception as e:
        print(f"Error parsing response: {e}")
        # Create a minimal valid report with improved model structure
        report = ChemicalToxicityAssessment(
            metadata=Metadata(
                data_completeness=DataCompleteness(
                    overall_score=0.5,
                    confidence_level="medium"
                ),
                last_updated=datetime.now().isoformat()
            ),
            chemical_properties=ChemicalProperties(
                description="Analysis pending"
            ),
            toxicity_mechanisms=ToxicityMechanisms(
                description="Analysis pending"
            ),
            clinical_evidence=ClinicalEvidence(
                description="Analysis pending"
            ),
            toxicity_risk_distribution=ToxicityRiskDistribution(
                explanation="Analysis pending",
                beta_parameters=BetaDistributionParameters(
                    alpha=1.0,
                    beta=1.0,
                    probability=0.5,
                    variance=0.083
                ),
                confidence_interval=ConfidenceInterval(
                    lower=0.1,
                    upper=0.9,
                    confidence_level=0.95
                ),
                interpretation="Analysis pending",
                limitations="Limited data available for analysis"
            ),
            risk_factors=RiskFactors()
        )
    
    return SearchState(**{**asdict(state), "report": report})

# ── assemble the graph ──────────────────────────────────────────────────────────
graph = StateGraph(SearchState)

graph.add_node("preprocess_and_generate_query", preprocess_and_generate_query)
graph.add_node("run_search", run_search)
graph.add_node("parse_results", parse_results)
graph.add_node("summarize_initial", summarize_initial)
graph.add_node("generate_follow_up", generate_follow_up)
graph.add_node("run_follow_up_search", run_follow_up_search)
graph.add_node("parse_follow_up", parse_follow_up)
graph.add_node("summarize_follow_up", summarize_follow_up)
graph.add_node("generate_report", generate_report)

# edges – strictly linear in this example
graph.set_entry_point("preprocess_and_generate_query")
graph.add_edge("preprocess_and_generate_query", "run_search")
graph.add_edge("run_search", "parse_results")
graph.add_edge("parse_results", "summarize_initial")
graph.add_edge("summarize_initial", "generate_follow_up")
graph.add_edge("generate_follow_up", "run_follow_up_search")
graph.add_edge("run_follow_up_search", "parse_follow_up")
graph.add_edge("parse_follow_up", "summarize_follow_up")
graph.add_edge("summarize_follow_up", "generate_report")
graph.set_finish_point("generate_report")

# ── compile an executor ─────────────────────────────────────────────────────────
executor = graph.compile()

@tool(description="This tool will allow you to look up information on the internet related to users queries. It will allow you to factually ground your answers and provide citations.")
def invoke_deepsearch(query: str):
    """
    Use this tool to perform a deep search for information.
    This tool is almost always useful when the user asks a question.
        Args:
        query (str): The user's question.
    """
    return executor.invoke({"original_query": query})

def _validate_references(report: ChemicalToxicityAssessment, search_results: List[Dict[str, Any]]):
    """Enhanced reference validation using the improved validation function."""
    # Use the improved validation function from toxicity_models
    validation_result = validate_reference_urls(report.references)
    
    # Also check if URLs are present in search results
    def extract_urls_from_search_results(search_results):
        return set(r['url'] for r in search_results if 'url' in r)
    
    search_urls = extract_urls_from_search_results(search_results)
    report_urls = {ref.url for ref in report.references if ref.url}
    missing_from_search = list(report_urls - search_urls)
    
    return {
        "validation_result": validation_result,
        "missing_from_search": missing_from_search,
        "valid": validation_result["summary"]["validity_rate"] == 1.0 and len(missing_from_search) == 0
    }

# Tool wrapper for agent use - simplified for OpenAI function calling
@tool(description="Validate that all references in the final report are accessible and present in the actual search results. Returns detailed validation results including URL accessibility checks.")
def validate_references(report_data: str, search_results: List[Dict[str, Any]]):
    """Validate references with simplified parameters for OpenAI compatibility"""
    try:
        # Parse the report data back to ChemicalToxicityAssessment
        report_dict = json.loads(report_data)
        report = ChemicalToxicityAssessment(**report_dict)
        return _validate_references(report, search_results)
    except Exception as e:
        return {"error": f"Failed to parse report data: {str(e)}"}

deeptox_agent = Agent(
    name="Deep Toxicology Agent",
    model=agent_model,
    tools=[get_chemprop, invoke_deepsearch],
    description=dedent("""
        You are a specialized toxicology research assistant with expertise in:
        - Chemical toxicity analysis and risk assessment
        - Scientific literature review and synthesis
        - Statistical analysis of toxicity data
        - Regulatory compliance and safety standards
        
        Your writing style is:
        - Scientifically rigorous and evidence-based
        - Clear and precise in technical terminology
        - Comprehensive in risk assessment
        - Properly cited with academic sources
    """),
    instructions=dedent("""
        You are a toxicology research assistant that creates structured toxicity assessments.
        
        Workflow:
        1. Use get_chemprop to obtain chemical properties
        2. Use invoke_deepsearch ONCE with the original user query to gather comprehensive clinical evidence and mechanistic information
        3. Output structured data using the Pydantic model
        
        IMPORTANT: Only call invoke_deepsearch ONCE with the original user query. Do not make multiple separate search calls for different aspects. The search tool will automatically perform comprehensive research including initial search and follow-up queries.
        
        Focus on:
        - Chemical properties and their relevance to toxicity
        - Toxicity mechanisms with supporting evidence
        - Clinical studies with specific data (sample size, positive cases, etc.)
        - Risk assessment with statistical analysis including beta distribution parameters
        - Risk factors and high-risk populations
        - Comprehensive references
        
        Output structured data only. Convert to markdown only if explicitly requested.
    """),
    output_schema=ChemicalToxicityAssessment,
    # show_tool_calls=True,
    # add_datetime_to_instructions=True,
    # stream_intermediate_steps=False,
    # stream=False,
    # debug_mode=True,
)

if __name__ == "__main__":
    response = deeptox_agent.run(
        "Is Methotrexate closely linked to hepatotoxicity in the presence of alcohol consumption or obesity-related metabolic conditions?") 
    response_data = response.content
    timestamp = datetime.now().isoformat().replace(':', '-')

    # Save the response
    if isinstance(response_data, ChemicalToxicityAssessment):
        # Save as JSON
        json_filename = f"response_data_{timestamp}.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(response_data.model_dump(), f, indent=2, ensure_ascii=False)
        print(f"\nSaved structured output to {json_filename}")
        
        # Convert to markdown and save
        from webserver.ai_service import convert_pydantic_to_markdown
        markdown_content = convert_pydantic_to_markdown(
            response_data.model_dump(),
            "Is Methotrexate closely linked to hepatotoxicity in the presence of alcohol consumption or obesity-related metabolic conditions?"
        )
        md_filename = f"response_data_{timestamp}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"Saved markdown report to {md_filename}")
        
    elif isinstance(response_data, dict):
        # Handle dict response
        json_filename = f"response_data_{timestamp}.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved structured output to {json_filename}")
        
        # Convert to markdown
        from webserver.ai_service import convert_pydantic_to_markdown
        markdown_content = convert_pydantic_to_markdown(
            response_data,
            "Is Methotrexate closely linked to hepatotoxicity in the presence of alcohol consumption or obesity-related metabolic conditions?"
        )
        md_filename = f"response_data_{timestamp}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"Saved markdown report to {md_filename}")
        
    else:
        # Handle string response (fallback)
        filename = f"response_data_{timestamp}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(str(response_data))
        print(f"\nSaved text output to {filename}")