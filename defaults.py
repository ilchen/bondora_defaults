# coding: utf-8
import datetime
import numpy as np
import pandas as pd
import functools
import requests
import io

now = datetime.date.today()
# Explanation of individual columns can be found at: https://www.bondora.com/en/public-reports
BONDORA_URL = "https://www.bondora.com/marketing/media/LoanData.zip"

def clean_df(df):
    df = df.drop(['ReportAsOfEOD', 'ListedOnUTC', 'BidsPortfolioManager', 'BiddingStartedOn', 'BidsApi', 'BidsManual',
             'LoanApplicationStartedDate',
             'ApplicationSignedHour', 'ApplicationSignedWeekday', 'Rating_V0', 'Rating_V1', 'Rating_V2'], axis=1)
    df = df[pd.notnull(df['Rating'])]
    #df.loc[:, 'LoanDate'] = pd.to_datetime(df['LoanDate'])
    #df.loc[:, 'DefaultDate'] = pd.to_datetime(df['DefaultDate'])
    #df.loc[:, 'ContractEndDate'] = pd.to_datetime(df['ContractEndDate'])
    return df

def reorder_rows(k):
    ''' This function rearranges the rows in a dataframe k to ensure AA loans come before A loans
    :param k: a DataFrame representing an outcome of a grouping operation on a Bondora's loan portfolio
    '''
    if len({'AA', 'A'} & set(k.index.levels[0])) == 2: # make sure 'AA' loans will show up before 'A', if any
        loc1, loc2 = k.index.levels[0].get_loc('AA'), k.index.levels[0].get_loc('A')
        if loc1 > loc2:
            idxes = list(k.index.levels[0])
            idxes[loc1], idxes[loc2] = idxes[loc2], idxes[loc1]
            new_idx = k.index.set_levels(idxes, 0)
            k = k.reindex(new_idx)
    return  k

def print_df(df):
    with pd.option_context('display.max_rows', None, 'display.max_columns', None): print(df)

def extract_needed_columns(df):
    from pandas.tseries.offsets import MonthEnd
    from operator import attrgetter
    df['Recovered'] = df.PrincipalRecovery + df.InterestRecovery #- df.PrincipalDebtServicingCost - df.InterestAndPenaltyDebtServicingCost
    df = df[['Rating', 'ProbabilityOfDefault', 'Country', 'LoanDate', 'LoanDuration', 'DefaultDate', 'ContractEndDate',
             'EAD1', 'Recovered']] # PlannedPrincipalPostDefault
    df = df[df['Country'] != 'SK']
    df['ttd'] = (df.DefaultDate.dt.to_period('M') - df.LoanDate.dt.to_period('M'))  # Time to contract's default, i.e. how long the loan was performing. -1 if still current
    df.ttd.fillna(value=MonthEnd(-1), inplace=True)
    df.ttd = df.ttd.apply(attrgetter('n')).astype('int')
    df['ttce'] = (df.ContractEndDate.dt.to_period('M') - df.LoanDate.dt.to_period('M')) # Time to contract's end date, i.e. the actual maturity
    df.ttce.fillna(value=MonthEnd(-1), inplace=True)
    df.ttce = df.ttce.apply(attrgetter('n')).astype('int')
    df['ttn'] = now # - datetime.timedelta(days=12)
    df.ttn = df.ttn.apply(pd.to_datetime)
    df['ttn'] = (df.ttn.dt.to_period('M') - df.LoanDate.dt.to_period('M')).apply(attrgetter('n')) # How long the loan was running
    df.ttn = df.ttn.astype('int')
    df = df[df.ttn >= 3]
    df['tt'] = np.where(df.ttce >= 0, np.where(df.ttn < df.ttce, df.ttn, df.ttce), df.ttn)

    return  df


def calculate_apriori_default_intensities(df, country, start_year, max_duration=60, ratings=('AA', 'A', 'B', 'C', 'D', 'E', 'F', 'HR')):
    ''' This function analyses Bondora's own a-priory default intensities that they calculated when pricing a loan
    :param df: a DataFrame representing Bondora's loan portfolio
    :param country: the country loans issued in which to analyze,
            one of 'EE' for Estonia, 'FI' for Finland, 'ES' for Spain
    :param start_year: will only inlcude loans originated in this year or later into analysis
    :param max_duration: only include loans whose duration is not greater than this
    :param ratings: a list specifying what ratings to include
    :return: a tuple with mean default intensities, the first part returns averages per year,
             the second per year and loan maturity
    '''
    grouped1 = df[(df['LoanDate'].dt.year >= start_year) & (df['Rating'].isin(ratings)) & (df['Country'] == country)
                  & (df['LoanDuration'] <= max_duration)]['ProbabilityOfDefault'].groupby([df['Rating'], df['LoanDate'].dt.year])
    grouped2 = df[(df['LoanDate'].dt.year >= start_year) & (df['Rating'].isin(ratings)) & (df['Country'] == country)
                  & (df['LoanDuration'] <= max_duration)]['ProbabilityOfDefault'].groupby([df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']])

    return  (grouped1.mean(), grouped2.mean())

def calculate_default_intensities_buckets(df, country, start_year):
    ''' This function calculates the actual default intensities per per country, rating, year of issuance, and duration
    
    :param df: a DataFrame representing Bondora's loan portfolio
    :param country: the country loans issued in which to analyze,
            one of 'EE' for Estonia, 'FI' for Finland, 'ES' for Spain
    :param start_year: will only inlcude loans originated in this year or later into analysis
    :return: a DataFrame containing default intensities and the number of loans from which they were calculated.
            The DataFrame is indexed by Rating, loan issue year, and duration.
    '''
    # Let's tackle Estonia first
    grp_ee = df[(df['LoanDate'].dt.year >= start_year) & (df['Country'] == country) & (df.ttd != -1)][
        'ProbabilityOfDefault'].groupby([df['ttd'], df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']])
    grp_ee_dflt = grp_ee.count()
    defaulted_maturities = grp_ee_dflt.index.get_level_values(0)

    grp_ee_surv = df[(df['LoanDate'].dt.year >= start_year) & (df['Country'] == country) & (df.ttd == -1)][
        'ProbabilityOfDefault'].groupby([df['tt'], df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']])
    grp_ee_surv_cnt = grp_ee_surv.count()
    maturities = list(set(grp_ee_surv_cnt.index.get_level_values(0)))
    ee_surv = []
    ee_default_probs = []
    ee_counts = df[(df['LoanDate'].dt.year >= start_year) & (df['Country'] == country)][
        'ProbabilityOfDefault'].groupby([ df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']]).count()

    ee_rr = df[(df['LoanDate'].dt.year >= start_year) & (df['Country'] == country) & (df.ttd != -1)][
        ['EAD1', 'Recovered']].groupby([df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']])
    ee_rr_cnt = ee_rr.sum()

    grp_ee_dflt = grp_ee.count()
    for i in range(0, len(maturities) - 1):
        eedf = grp_ee_surv_cnt[i]
        for j in reversed(range(i + 1, len(maturities))):
            eedf = eedf.add(grp_ee_surv_cnt[j], fill_value=0)
        # eedf = eedf.astype('int64')
        ee_surv.append(eedf)
    ee_surv.append(grp_ee_surv_cnt[len(maturities) - 1])

    for i in range(len(maturities)):
        if i in defaulted_maturities:
            eedf = ee_surv[i].add(grp_ee_dflt[i], fill_value=0)
            ee_default_probs.append(grp_ee_dflt[i].div(eedf, fill_value=0))
        else:
            ee_default_probs.append(0)

    # End now let's calculate the annual default intensity
    avg_monthly_dflt_intensity = functools.reduce(lambda x, y: x.add(y, fill_value=0), ee_default_probs[3:])

    # avg_monthly_dflt_intensity = functools.reduce(lambda x, y: x.add(y, fill_value=0), ee_default_probs[3:15])

    cur_year = now.year
    cur_month = now.month

    for year in range(start_year, cur_year):
       avg_monthly_dflt_intensity.loc[:, year:year] /= 12 * (cur_year - year - 1) + 9. + cur_month
    avg_monthly_dflt_intensity.loc[:, cur_year:cur_year] /= cur_month - 3.

    # avg_monthly_dflt_intensity.loc[:, :cur_year - 2] /= 12.

    # # Let's deal with last year
    # if cur_month < 4:
    #     avg_monthly_dflt_intensity.loc[:, cur_year-1:cur_year-1] /= 9. + cur_month - 1
    # else:
    #     avg_monthly_dflt_intensity.loc[:, cur_year-1:cur_year-1] /= 12.
    #
    # # And finally the current year
    # avg_monthly_dflt_intensity.loc[:, cur_year:cur_year] /= cur_month - 4.

    # Proper approximation
    annual_dflt_intensity = -avg_monthly_dflt_intensity
    annual_dflt_intensity = 1. - np.exp(annual_dflt_intensity * 12)

    annual_dflt_intensity = pd.concat([annual_dflt_intensity, ee_rr_cnt.Recovered / ee_rr_cnt.EAD1], axis=1)
    annual_dflt_intensity = pd.concat([annual_dflt_intensity, ee_counts], axis=1)

    annual_dflt_intensity.columns = ['Annual Default Intensity', 'Recovery Rate', '#']
    annual_dflt_intensity['Recovery Rate'] = np.where(pd.isnull(annual_dflt_intensity['Recovery Rate']), '-----',
                                                      (annual_dflt_intensity['Recovery Rate']*100.).round(2).astype(str) + '%')

    if len({'AA', 'A'} & set(annual_dflt_intensity.index.levels[0])) == 2: # make sure 'AA' loans will show up before 'A', if any
        loc1, loc2 = annual_dflt_intensity.index.levels[0].get_loc('AA'), annual_dflt_intensity.index.levels[0].get_loc('A')
        if loc1 > loc2:
            idxes = list(annual_dflt_intensity.index.levels[0])
            idxes[loc1], idxes[loc2] = idxes[loc2], idxes[loc1]
            new_idx = annual_dflt_intensity.index.set_levels(idxes, 0)
            annual_dflt_intensity = annual_dflt_intensity.reindex(new_idx)

    annual_dflt_intensity['#'] = annual_dflt_intensity['#'].fillna(0).astype('int')
    return  annual_dflt_intensity

def default_incidence(s):
    num_defaulted = s[s == False].count()
    total_num = s.count()
    return num_defaulted / total_num, num_defaulted, total_num

def check_probability_of_default(df, country):
    ''' This function compares Bondora's a priori defaul probabilities with actual frequencies of default. It prints
    a Series object whose values are tuples containing 3 values (Default frequency, Number loans defaulted, Total number of loans)
    :param df: a DataFrame representing Bondora's loan portfolio
    :param country: the country loans issued in which to analyze,
            one of 'EE' for Estonia, 'FI' for Finland, 'ES' for Spain
    :return: None 
    '''
    categories = pd.cut(df[(df.Country == country)].ProbabilityOfDefault, [x / 1000. for x in range(0, 1001, 25)])
    grouped = df[(df.Country == country)]['DefaultDate'].isnull().groupby(
        [categories, df['Rating'], df['LoanDate'].dt.year])
    k = grouped.agg(default_incidence)
    k.name = '(Default frequency, Number defaulted, Total number of loans)'
    if len({'AA', 'A'} & set(k.index.levels[0])) == 2: # make sure 'AA' loans will show up before 'A', if any
        loc1, loc2 = k.index.levels[0].get_loc('AA'), k.index.levels[0].get_loc('A')
        if loc1 > loc2:
            idxes = list(k.index.levels[0])
            idxes[loc1], idxes[loc2] = idxes[loc2], idxes[loc1]
            new_idx = k.index.set_levels(idxes, 0)
            k = k.reindex(new_idx)
    with pd.option_context('display.max_rows', None, 'display.max_columns', None): print(k)

with requests.get(BONDORA_URL) as s:
    df = pd.read_csv(io.BytesIO(s.content), index_col=['LoanId'],
                     infer_datetime_format=True, parse_dates=['LoanDate', 'DefaultDate', 'ContractEndDate'],
                     compression='zip')

# df = pd.read_csv('~/Downloads/LoanData-3.csv', index_col=['LoanId'],
#                  infer_datetime_format=True, parse_dates=['LoanDate', 'DefaultDate', 'ContractEndDate'])
df = clean_df(df)
df = extract_needed_columns(df)

# Analysis of Bondora's own a priori probabilities of default for different loans
calculate_apriori_default_intensities(df, 'EE', 2015)
calculate_apriori_default_intensities(df, 'EE', 2018, ratings=['AA', 'A'])
apr_ee_short, apr_ee = map(reorder_rows, calculate_apriori_default_intensities(df, 'EE', 2018, ratings=['AA', 'A'], max_duration=12))
print_df(apr_ee_short)

# Deriving probabilities of default based on actual defaults
ee = calculate_default_intensities_buckets(df, 'EE', 2015)
fi = calculate_default_intensities_buckets(df, 'FI', 2015)

# Analysis of derived default intensities
ee.loc[(['AA','A','B'], [2017,2018]), :]
ee['Annual Default Intensity'].loc[['AA','A','B'], [2017,2018]]

apr_ee = calculate_apriori_default_intensities(df, 'EE', 2017, ratings=['AA', 'A', 'B'])
apostr_ee = ee.loc[(['AA','A', 'B'], [2017,2018,2019]), :]
combined_ee = pd.concat([apr_ee, apostr_ee], axis=1)
combined_ee['underestimate of default intensity']=combined_ee['Annual Default Intensity']-combined_ee['ProbabilityOfDefault']
combined_ee.loc['AA', 'underestimate of default intensity'].plot(grid=True, title='Estonia AA: underestimates of default intensity')
combined_ee.loc['A', 'underestimate of default intensity'].plot(grid=True, title='Estonia A: underestimates of default intensity')
combined_ee.loc['B', 'underestimate of default intensity'].plot(grid=True, title='Estonia B: underestimates of default intensity')
combined_ee.loc[['AA', 'A'], 'underestimate of default intensity']

apr_fi = calculate_apriori_default_intensities(df, 'FI', 2017, ratings=['AA', 'A', 'B'])
apostr_fi = fi.loc[(['AA','A', 'B'], [2017,2018,2019]), :]
combined_fi = pd.concat([apr_fi, apostr_fi], axis=1)
combined_fi['underestimate of default intensity']=combined_fi['Annual Default Intensity']-combined_fi['ProbabilityOfDefault']
combined_fi.loc['AA', 'underestimate of default intensity'].plot(grid=True, legend=True, x='Finland AA: underestimates of default intensity')
combined_fi.loc['A', 'underestimate of default intensity'].plot(grid=True, x='Finland A: underestimates of default intensity')
combined_fi.loc['B', 'underestimate of default intensity'].plot(grid=True, x='Finland B: underestimates of default intensity')
combined_fi.loc[['AA', 'A'], 'underestimate of default intensity']


ee_rrs = [
    df[(df['LoanDate'].dt.year >= 2015) & (df['Country'] == 'EE') & (df.ttd != -1)][ # Calculating based on the loan issue date
        ['EAD1', 'Recovered']].groupby([df['Rating'], df['LoanDate'].dt.year]),
    df[(df['DefaultDate'].dt.year >= 2015) & (df['Country'] == 'EE') & (df.ttd != -1)][ # Calculating based on the loan default date
        ['EAD1', 'Recovered']].groupby([df['Rating'], df['DefaultDate'].dt.year])]
for ee_rr_cnt in [ee_rr.sum() for ee_rr in ee_rrs]:
    ee_rr_cnt['Recovery Rate']=ee_rr_cnt.Recovered / ee_rr_cnt.EAD1
    ee_rr_cnt=ee_rr_cnt.drop(['EAD1', 'Recovered'], axis=1)
    ee_rr_cnt['Recovery Rate'] = np.where(pd.isnull(ee_rr_cnt['Recovery Rate']), '-----',
                                                   (ee_rr_cnt['Recovery Rate']*100.).round(2).astype(str) + '%')
    with pd.option_context('display.max_rows', None, 'display.max_columns', None):
        print(ee_rr_cnt)

fi_rrs = [
    df[(df['LoanDate'].dt.year >= 2015) & (df['Country'] == 'FI') & (df.ttd != -1)][ # Calculating based on the loan issue date
        ['EAD1', 'Recovered']].groupby([df['Rating'], df['LoanDate'].dt.year]),
    df[(df['DefaultDate'].dt.year >= 2015) & (df['Country'] == 'FI') & (df.ttd != -1)][ # Calculating based on the loan default date
        ['EAD1', 'Recovered']].groupby([df['Rating'], df['DefaultDate'].dt.year])]
for fi_rr_cnt in [fi_rr.sum() for fi_rr in fi_rrs]:
    fi_rr_cnt['Recovery Rate']=fi_rr_cnt.Recovered / fi_rr_cnt.EAD1
    fi_rr_cnt=fi_rr_cnt.drop(['EAD1', 'Recovered'], axis=1)
    fi_rr_cnt['Recovery Rate'] = np.where(pd.isnull(fi_rr_cnt['Recovery Rate']), '-----',
                                                   (fi_rr_cnt['Recovery Rate']*100.).round(2).astype(str) + '%')
    with pd.option_context('display.max_rows', None, 'display.max_columns', None):
        print(fi_rr_cnt)


ee_rr_cnt = df[(df['DefaultDate'].dt.year >= 2015) & (df['Country'] == 'EE') & (df.ttd != -1)][ # Calculating based on the loan default date
        ['EAD1', 'Recovered']].groupby([df['Rating'], df['DefaultDate'].dt.year, df['LoanDuration']]).sum()