# bondora_defaults
Analysis of bondora loans' probabilities of default. I use both Bondora's own probabilities of default as captured in [the ProbabilityOfDefault column](https://www.bondora.com/en/public-reports#shared-legend), as well as make my own effort to derive them.

## Notes
There are two main functions in the script:
* `printProbabilities` that analyses bondora's own a priory probabilities of default
* `calculateBuckets`  that looks at the actual loans and then derives observed default intensities based on the actual number of loans that defaulted per country, rating, year of issuance, and duration.

**NB:** This software is provided as is, it may contain mistakes and report mistaken outcomes. Please use it on condition that I hold no responsibility for decisions made based on the outcomes this software provides.