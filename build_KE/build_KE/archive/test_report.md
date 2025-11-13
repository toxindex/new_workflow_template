# Key Event Extraction Report: endocrine disruption

## Summary Statistics

- **Total Key Events**: 7
  - MIE (Molecular Initiating Events): 1
  - KE (Key Events): 5
  - AO (Adverse Outcomes): 1

- **Total Relationships**: 6

- **Total Evidence Records**: 6

## Events by Biological Level

- **Cellular**: 2
- **Molecular**: 1
- **Organ**: 1
- **Organism**: 2
- **Tissue**: 1

## Evidence Count per Key Event

- **Increased follicular atresia in ovary**: 3 evidence record(s)
- **Increased apoptosis of granulosa cells in ovary**: 2 evidence record(s)
- **Decreased estradiol synthesis in ovary**: 2 evidence record(s)
- **Increased menstrual cycle length**: 2 evidence record(s)
- **Decreased FSH levels in blood**: 1 evidence record(s)
- **Necrosis of granulosa cells in ovary**: 1 evidence record(s)
- **Reduced fertility**: 1 evidence record(s)

## Example AOP Pathway

The following is an example pathway extracted from the document:

1. **Decreased FSH levels in blood** [EventType.MIE] (BiologicalLevel.MOLECULAR) → 
2. **Increased apoptosis of granulosa cells in ovary** [EventType.KE] (BiologicalLevel.CELLULAR) → 
3. **Increased follicular atresia in ovary** [EventType.KE] (BiologicalLevel.TISSUE) → 
4. **Decreased estradiol synthesis in ovary** [EventType.KE] (BiologicalLevel.ORGAN) → 
5. **Increased menstrual cycle length** [EventType.KE] (BiologicalLevel.ORGANISM) → 
6. **Reduced fertility** [EventType.AO] (BiologicalLevel.ORGANISM)

**Pathway Details:**
- Step 1 → 2: Evidence strength = 0.70
  *The article provides strong mechanistic plausibility for this relationship. The authors propose that the observed negative correlation between n-hexane/2,5-HD exposure and FSH levels (Figure 4) leads ...*
- Step 2 → 3: Evidence strength = 0.90
  *The relationship between increased granulosa cell apoptosis and increased follicular atresia is a direct, mechanistic one, as follicular atresia is the process of follicle degeneration primarily drive...*
- Step 3 → 4: Evidence strength = 0.70
  *The paper provides strong mechanistic plausibility for this relationship. Increased follicular atresia is characterized by apoptosis of granulosa cells. The paper cites in vitro studies where 2,5-HD (...*
- Step 4 → 5: Evidence strength = 0.40
  *The study presents suggestive evidence for this relationship. A trend towards lower estradiol levels was observed in a subgroup of exposed women with oligomenorrhea (p=0.059), which is biologically co...*
- Step 5 → 6: Evidence strength = 0.80
  *The article provides strong evidence for an association between increased menstrual cycle length and reduced fertility. A statistically significant positive correlation was found in the exposed group ...*