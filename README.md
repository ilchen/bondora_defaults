# bondora_defaults
Analysis of bondora loans' probabilities of default. I use both Bondora's own probabilities of default as captured in [the ProbabilityOfDefault column](https://www.bondora.com/en/public-reports#shared-legend), as well as make my own effort to derive them.

## Notes
There are three main functions in the script:
* `print_apriori_probabilities` that analyses bondora's own a priory probabilities of default
* `calculate_default_intensities_buckets`  that looks at the actual loans and then derives observed default intensities based on the actual number of loans that defaulted per country, rating, year of issuance, and duration.
* `check_probability_of_default`  that compares Bondora's a priori defaul probabilities with actual frequencies of default. It prints a Series object whose values are tuples containing 3 values (Default frequency, Number loans defaulted, Total number of loans)

**NB:** This software is provided as is, it may contain mistakes and report wrong outcomes. Please use it on condition that I hold no responsibility for decisions made based on the outcomes this software provides.