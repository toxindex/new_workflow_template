from __future__ import annotations
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
import re
from urllib.parse import urlparse
from datetime import datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Improved Beta Distribution Model
class BetaDistributionParameters(BaseModel):
    alpha: float = Field(..., gt=0, description="Alpha parameter (positive cases + 1)")
    beta: float = Field(..., gt=0, description="Beta parameter (total - positive cases + 1)")
    probability: float = Field(..., ge=0, le=1, description="Mean probability (alpha / (alpha + beta))")
    variance: float = Field(..., ge=0, description="Variance of the distribution")
    
    @validator('alpha', 'beta')
    def validate_parameters(cls, v):
        if v <= 0:
            raise ValueError("Alpha and beta must be positive")
        return v
    
    @validator('probability')
    def validate_probability(cls, v):
        if not 0 <= v <= 1:
            raise ValueError("Probability must be between 0 and 1")
        return v

class ConfidenceInterval(BaseModel):
    lower: float = Field(..., description="Lower bound of confidence interval")
    upper: float = Field(..., description="Upper bound of confidence interval")
    confidence_level: float = Field(..., ge=0.5, le=0.99, description="Confidence level (e.g., 0.95 for 95%)")
    
    @validator('lower', 'upper')
    def validate_bounds(cls, v):
        if not 0 <= v <= 1:
            raise ValueError("Confidence bounds must be between 0 and 1")
        return v
    
    @validator('upper')
    def validate_upper_greater_than_lower(cls, v, values):
        if 'lower' in values and v <= values['lower']:
            raise ValueError("Upper bound must be greater than lower bound")
        return v

class StudyForBetaCalculation(BaseModel):
    title: str = Field(..., description="Title of the study")
    url: str = Field(..., description="URL of the study")
    sample_size: int = Field(..., gt=0, description="Sample size of the study")
    positive_cases: int = Field(..., ge=0, description="Number of positive cases")
    weight: float = Field(..., ge=0, le=1, description="Weight of this study in the calculation")
    contribution: str = Field(..., description="How this study contributes to the calculation")
    confidence: str = Field(..., description="Confidence level: high, medium, or low")
    
    @validator('positive_cases')
    def validate_positive_cases(cls, v, values):
        if 'sample_size' in values and v > values['sample_size']:
            raise ValueError("Positive cases cannot exceed sample size")
        return v

class ToxicityRiskDistribution(BaseModel):
    explanation: str = Field(..., description="Explanation of the risk distribution")
    beta_parameters: BetaDistributionParameters = Field(..., description="Beta distribution parameters")
    confidence_interval: ConfidenceInterval = Field(..., description="Confidence interval for the risk estimate")
    studies_used: List[StudyForBetaCalculation] = Field(default=[], description="Studies used for calculation")
    interpretation: str = Field(..., description="Interpretation of the risk distribution")
    limitations: str = Field(..., description="Limitations of the analysis")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")

# Improved Reference Validation
class Reference(BaseModel):
    title: str = Field(..., description="Title of the reference")
    authors: str = Field(default="", description="Authors of the reference")
    year: int = Field(default=0, description="Year of publication")
    url: str = Field(default="", description="URL of the reference")
    type: str = Field(default="", description="Type of reference")
    relevance: str = Field(default="", description="Relevance to the analysis")
    
    @validator('url')
    def validate_url(cls, v):
        if not v:
            return v
        # Check if URL is not a placeholder
        if v.lower() in ['n/a', 'none', 'unknown', 'example.com', 'placeholder']:
            raise ValueError("URL cannot be a placeholder value")
        
        # Basic URL format validation
        try:
            result = urlparse(v)
            if not all([result.scheme, result.netloc]):
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError("Invalid URL format")
        
        return v
    
    @validator('year')
    def validate_year(cls, v):
        if v < 1900 or v > 2030:
            raise ValueError("Year must be between 1900 and 2030")
        return v

# Enhanced Reference Validation Function
def validate_reference_urls(references: List[Reference]) -> Dict[str, Any]:
    """Validate reference URLs for accessibility and authenticity."""
    
    
    results = {
        "valid": [],
        "invalid": [],
        "unreachable": [],
        "summary": {}
    }
    
    def check_url(reference: Reference) -> Dict[str, Any]:
        if not reference.url:
            return {"reference": reference, "status": "no_url", "valid": False}
        
        try:
            # Check if URL is accessible
            response = requests.head(reference.url, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                return {"reference": reference, "status": "accessible", "valid": True}
            else:
                return {"reference": reference, "status": f"http_{response.status_code}", "valid": False}
        except Exception as e:
            return {"reference": reference, "status": "unreachable", "error": str(e), "valid": False}
    
    # Check URLs in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ref = {executor.submit(check_url, ref): ref for ref in references}
        
        for future in as_completed(future_to_ref):
            result = future.result()
            if result["valid"]:
                results["valid"].append(result)
            else:
                if result["status"] == "unreachable":
                    results["unreachable"].append(result)
                else:
                    results["invalid"].append(result)
    
    # Summary
    total = len(references)
    valid = len(results["valid"])
    invalid = len(results["invalid"])
    unreachable = len(results["unreachable"])
    
    results["summary"] = {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "unreachable": unreachable,
        "validity_rate": valid / total if total > 0 else 0
    }
    
    return results

# Core Models
class DataCompleteness(BaseModel):
    overall_score: float = Field(..., ge=0, le=1, description="Overall data completeness score (0-1)")
    missing_fields: List[str] = Field(default=[], description="List of missing data fields")
    confidence_level: str = Field(..., description="Confidence level: high, medium, or low")

class Metadata(BaseModel):
    data_completeness: DataCompleteness = Field(..., description="Data completeness assessment")
    last_updated: str = Field(..., description="Last update timestamp in ISO format")
    data_sources: List[str] = Field(default=[], description="List of data sources used")
    reference_revision_attempts: int = Field(default=0, description="Number of reference revision attempts")

class ChemicalProperty(BaseModel):
    name: str = Field(..., description="Name of the chemical property")
    value: str = Field(..., description="Value of the property")
    relevance: str = Field(..., description="Relevance to toxicity")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")

class ChemicalProperties(BaseModel):
    description: str = Field(..., description="Description of chemical properties")
    properties: List[ChemicalProperty] = Field(default=[], description="List of chemical properties")
    evidence: List[str] = Field(default=[], description="Supporting evidence for properties")

class ToxicityMechanism(BaseModel):
    name: str = Field(..., description="Name of the toxicity mechanism")
    description: str = Field(..., description="Description of the mechanism")
    evidence: str = Field(..., description="Evidence supporting this mechanism")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")
    references: List[str] = Field(default=[], description="References supporting this mechanism")

class ToxicityMechanisms(BaseModel):
    description: str = Field(..., description="Description of toxicity mechanisms")
    mechanisms: List[ToxicityMechanism] = Field(default=[], description="List of toxicity mechanisms")

class ClinicalStudy(BaseModel):
    title: str = Field(..., description="Title of the clinical study")
    type: str = Field(..., description="Type of study (e.g., clinical trial, case study)")
    sample_size: int = Field(..., gt=0, description="Sample size of the study")
    positive_cases: int = Field(..., ge=0, description="Number of positive cases")
    duration: str = Field(..., description="Study duration")
    dosage: str = Field(..., description="Dosage information")
    demographics: str = Field(..., description="Patient demographics")
    findings: str = Field(..., description="Study findings")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")
    references: List[str] = Field(default=[], description="References for this study")
    
    @validator('positive_cases')
    def validate_positive_cases(cls, v, values):
        if 'sample_size' in values and v > values['sample_size']:
            raise ValueError("Positive cases cannot exceed sample size")
        return v

class TreatmentProtocol(BaseModel):
    name: str = Field(..., description="Name of the treatment protocol")
    description: str = Field(..., description="Description of the protocol")
    effectiveness: str = Field(..., description="Effectiveness of the treatment")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")
    references: List[str] = Field(default=[], description="References for this protocol")

class ClinicalEvidence(BaseModel):
    description: str = Field(..., description="Description of clinical evidence")
    studies: List[ClinicalStudy] = Field(default=[], description="List of clinical studies")
    treatment_protocols: List[TreatmentProtocol] = Field(default=[], description="List of treatment protocols")

class RiskGroup(BaseModel):
    group: str = Field(..., description="High-risk group name")
    risk_level: str = Field(..., description="Risk level: high, medium, or low")
    explanation: str = Field(..., description="Explanation of the risk")
    evidence: str = Field(..., description="Evidence supporting this risk assessment")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")

class ModifyingFactor(BaseModel):
    factor: str = Field(..., description="Modifying factor name")
    effect: str = Field(..., description="Effect of the factor")
    evidence: str = Field(..., description="Evidence for this factor")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")

class PreventiveMeasure(BaseModel):
    measure: str = Field(..., description="Preventive measure name")
    effectiveness: str = Field(..., description="Effectiveness of the measure")
    evidence: str = Field(..., description="Evidence for this measure")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")

class RiskFactors(BaseModel):
    high_risk_groups: List[RiskGroup] = Field(default=[], description="List of high-risk groups")
    modifying_factors: List[ModifyingFactor] = Field(default=[], description="List of modifying factors")
    preventive_measures: List[PreventiveMeasure] = Field(default=[], description="List of preventive measures")
    extra_notes: str = Field(default="", description="Additional risk-related notes")

class ChemicalToxicityAssessment(BaseModel):
    metadata: Metadata = Field(..., description="Metadata about the assessment")
    chemical_properties: ChemicalProperties = Field(..., description="Chemical properties analysis")
    toxicity_mechanisms: ToxicityMechanisms = Field(..., description="Toxicity mechanisms analysis")
    clinical_evidence: ClinicalEvidence = Field(..., description="Clinical evidence analysis")
    toxicity_risk_distribution: ToxicityRiskDistribution = Field(..., description="Risk distribution analysis")
    risk_factors: RiskFactors = Field(..., description="Risk factors analysis")
    references: List[Reference] = Field(default=[], description="List of references")
    
    def validate_references(self) -> Dict[str, Any]:
        """Validate all references in the assessment."""
        return validate_reference_urls(self.references)
    
    def get_beta_distribution_summary(self) -> Dict[str, Any]:
        """Get a summary of the beta distribution analysis."""
        risk_dist = self.toxicity_risk_distribution
        return {
            "probability": risk_dist.beta_parameters.probability,
            "confidence_interval": {
                "lower": risk_dist.confidence_interval.lower,
                "upper": risk_dist.confidence_interval.upper,
                "level": risk_dist.confidence_interval.confidence_level
            },
            "studies_count": len(risk_dist.studies_used),
            "confidence": risk_dist.confidence
        }
    
    def get_reference_quality_report(self) -> Dict[str, Any]:
        """Get a quality report for all references."""
        validation_result = self.validate_references()
        return {
            "total_references": validation_result["summary"]["total"],
            "valid_references": validation_result["summary"]["valid"],
            "invalid_references": validation_result["summary"]["invalid"],
            "unreachable_references": validation_result["summary"]["unreachable"],
            "validity_rate": validation_result["summary"]["validity_rate"],
            "details": validation_result
        } 