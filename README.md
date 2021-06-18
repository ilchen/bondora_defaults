# Bondora defaults and recoveries
Analysis of Bondora loans' probabilities of default and recovery rates. I use both Bondora's own probabilities of default
as captured in [the ProbabilityOfDefault column](https://www.bondora.com/en/public-reports#shared-legend), as well as
make my own effort to derive them.

This is different from [expected losses data](https://support.bondora.com/en/how-are-bondora-risk-ratings-calculated) Bondora publishes (this data gives a picture of net expected losses that takes expected recovery
over a long period of time).

If you care about optimizing your investments for avoiding defaults rather than for debt recovery from defaulted loans,
you might find it useful. Feel free to fork and enhance, this is merely a first try.

I also calculated the actual recovery rate for each bucket of loans (country, year, maturity) based on the percentage of outstanding principal recovered less costs:
```
PrincipalRecovery + InterestRecovery
------------------------------------ X 100%
               EAD1
```

## How to run
```commandline
jupyter notebook bondora_defaults.ipynb 
```

You can also run the notebook in Google cloud. This way you don't need to install anything locally. This takes just a few seconds:
1. Go to [Google Colaboratory](https://colab.research.google.com/notebooks/intro.ipynb#recent=true) in your browser
2. In the modal window that appears select `GitHub`
3. Enter the URL of this repository's notebook: `https://github.com/ilchen/bondora_defaults/blob/master/bondora_defaults.ipynb`
4. Click the search icon
5. Enjoy

## How to just inspect the results
If for some reason you don't have time to run the notebook, you can simply navigate to [its latest run](https://github.com/ilchen/bondora_defaults/blob/master/bondora_defaults.ipynb)
and the scroll down to the analysis featuring graphs like the ones below:

![A-priory annual default rates for Estonia](https://github.com/ilchen/bondora_defaults/blob/master/ext/ee_apri.png?raw=true)

![Actual annual default rates for Estonia](https://github.com/ilchen/bondora_defaults/blob/master/ext/ee_act.png?raw=true)

...

## Notes
There are three main functions in the script:
* `calculate_apriori_default_intensities` that analyses bondora's own a priory probabilities of default
* `calculate_default_intensities_buckets`  that looks at the actual loans and then derives observed default intensities based on the actual number of loans that defaulted per country, rating, year of issuance, and duration.
* `check_probability_of_default`  that compares Bondora's a-priori defaul probabilities with actual frequencies of default. It prints a Series object whose values are tuples containing 3 values (Default frequency, Number loans defaulted, Total number of loans)

**NB:** This software is provided as is, it may contain mistakes and report wrong outcomes. Please use it on condition that I hold no responsibility for decisions made based on the outcomes this software provides.

