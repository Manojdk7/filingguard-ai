# Known Limitations & Validation Assumptions

1. **Operating Expenses Presentation**: Operating expenses are parsed from reported Inline XBRL line items (`OperatingExpenses`). If omitted in filing presentation (e.g. single-step format), the engine marks the presentation check as `NOT_EVALUATED` rather than inventing figures.
2. **Material Anomaly $\neq$ Fraud**: A warning on YoY variance (such as Apple's +52.02% equity increase) flags significant operational or capital structure events for auditor review; it is never labelled as fraud.
3. **Cross-Statement Scope**: Cross-statement checks require exact alignment of entity, duration, and unit before comparison, guarding against false divergence alerts.
4. **Correction Immutability**: Reviewer corrections strictly preserve original SEC-reported facts in `company_facts` and `xbrl_parsed_facts`; corrected values are persisted exclusively in `human_reviews` and evaluated dynamically via `fact_overrides`.
5. **Tamper-Evident History**: SQLite tables can be accessed or altered by superusers at the storage layer; the cryptographic hash chain does not make local disk blocks physically unwriteable, but guarantees that any modification, reordering, or deletion is mathematically detected and localized upon verification.
6. **Benchmark Scope**: Prototype benchmark evaluates 28 reference facts across Apple, Microsoft, and Amazon. Non-standard presentations (e.g. Amazon missing separate gross profit line item in standard taxonomy facts) are transparently recorded as missing rather than imputed.

