from __future__ import annotations
from typing import List, Dict, Any
from pydantic import BaseModel, Field, validator
from urllib.parse import urlparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Simplified Beta Distribution Model (no description fields)
class BetaDistributionParameters(BaseModel):
    alpha: float = Field(..., gt=0)
    beta: float = Field(..., gt=0)
    probability: float = Field(..., ge=0, le=1)
    variance: float = Field(..., ge=0)
    
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
    lower: float = Field(..., ge=0, le=1)
    upper: float = Field(..., ge=0, le=1)
    confidence_level: float = Field(..., ge=0.5, le=0.99)
    
    @validator('upper')
    def validate_upper_greater_than_lower(cls, v, values):
        if 'lower' in values and v <= values['lower']:
            raise ValueError("Upper bound must be greater than lower bound")
        return v

class StudyForBetaCalculation(BaseModel):
    title: str = Field(...)
    url: str = Field(...)
    sample_size: int = Field(..., gt=0)
    positive_cases: int = Field(..., ge=0)
    weight: float = Field(..., ge=0, le=1)
    contribution: str = Field(...)
    confidence: str = Field(...)
    
    @validator('positive_cases')
    def validate_positive_cases(cls, v, values):
        if 'sample_size' in values and v > values['sample_size']:
            raise ValueError("Positive cases cannot exceed sample size")
        return v

class ToxicityRiskDistribution(BaseModel):
    explanation: str = Field(...)
    beta_parameters: BetaDistributionParameters = Field(...)
    confidence_interval: ConfidenceInterval = Field(...)
    studies_used: List[StudyForBetaCalculation] = Field(default=[])
    interpretation: str = Field(...)
    limitations: str = Field(...)
    confidence: str = Field(default="medium")

# Simplified Reference Model (no description fields)
class Reference(BaseModel):
    title: str = Field(...)
    authors: str = Field(default="")
    year: int = Field(default=0)
    url: str = Field(default="")
    type: str = Field(default="")
    relevance: str = Field(default="")
    
    @validator('url')
    def validate_url(cls, v):
        if not v:
            return v
        if v.lower() in ['n/a', 'none', 'unknown', 'example.com', 'placeholder']:
            raise ValueError("URL cannot be a placeholder value")
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
            response = requests.head(reference.url, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                return {"reference": reference, "status": "accessible", "valid": True}
            else:
                return {"reference": reference, "status": f"http_{response.status_code}", "valid": False}
        except Exception as e:
            return {"reference": reference, "status": "unreachable", "error": str(e), "valid": False}
    
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

# Simplified Core Models (no description fields)
class DataCompleteness(BaseModel):
    overall_score: float = Field(..., ge=0, le=1)
    missing_fields: List[str] = Field(default=[])
    confidence_level: str = Field(...)

class Metadata(BaseModel):
    data_completeness: DataCompleteness = Field(...)
    last_updated: str = Field(...)
    data_sources: List[str] = Field(default=[])
    reference_revision_attempts: int = Field(default=0)

class ChemicalProperty(BaseModel):
    name: str = Field(...)
    value: str = Field(...)
    relevance: str = Field(...)
    confidence: str = Field(default="medium")

class ChemicalProperties(BaseModel):
    description: str = Field(...)
    properties: List[ChemicalProperty] = Field(default=[])
    evidence: List[str] = Field(default=[])

class ToxicityMechanism(BaseModel):
    name: str = Field(...)
    description: str = Field(...)
    evidence: str = Field(...)
    confidence: str = Field(default="medium")
    references: List[str] = Field(default=[])

class ToxicityMechanisms(BaseModel):
    description: str = Field(...)
    mechanisms: List[ToxicityMechanism] = Field(default=[])

class ClinicalStudy(BaseModel):
    title: str = Field(...)
    type: str = Field(...)
    sample_size: int = Field(..., gt=0)
    positive_cases: int = Field(..., ge=0)
    duration: str = Field(...)
    dosage: str = Field(...)
    demographics: str = Field(...)
    findings: str = Field(...)
    confidence: str = Field(default="medium")
    references: List[str] = Field(default=[])
    
    @validator('positive_cases')
    def validate_positive_cases(cls, v, values):
        if 'sample_size' in values and v > values['sample_size']:
            raise ValueError("Positive cases cannot exceed sample size")
        return v

class TreatmentProtocol(BaseModel):
    name: str = Field(...)
    description: str = Field(...)
    effectiveness: str = Field(...)
    confidence: str = Field(default="medium")
    references: List[str] = Field(default=[])

class ClinicalEvidence(BaseModel):
    description: str = Field(...)
    studies: List[ClinicalStudy] = Field(default=[])
    treatment_protocols: List[TreatmentProtocol] = Field(default=[])

class RiskGroup(BaseModel):
    group: str = Field(...)
    risk_level: str = Field(...)
    explanation: str = Field(...)
    evidence: str = Field(...)
    confidence: str = Field(default="medium")

class ModifyingFactor(BaseModel):
    factor: str = Field(...)
    effect: str = Field(...)
    evidence: str = Field(...)
    confidence: str = Field(default="medium")

class PreventiveMeasure(BaseModel):
    measure: str = Field(...)
    effectiveness: str = Field(...)
    evidence: str = Field(...)
    confidence: str = Field(default="medium")

class RiskFactors(BaseModel):
    high_risk_groups: List[RiskGroup] = Field(default=[])
    modifying_factors: List[ModifyingFactor] = Field(default=[])
    preventive_measures: List[PreventiveMeasure] = Field(default=[])
    extra_notes: str = Field(default="")

class ChemicalToxicityAssessment(BaseModel):
    metadata: Metadata = Field(...)
    chemical_properties: ChemicalProperties = Field(...)
    toxicity_mechanisms: ToxicityMechanisms = Field(...)
    clinical_evidence: ClinicalEvidence = Field(...)
    toxicity_risk_distribution: ToxicityRiskDistribution = Field(...)
    risk_factors: RiskFactors = Field(...)
    references: List[Reference] = Field(default=[])
    
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