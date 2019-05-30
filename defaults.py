# coding: utf-8
import datetime
import numpy as np
import pandas as pd
import functools
import requests
import io

now = datetime.date.today()
BONDORA_URL = "https://www.bondora.com/marketing/media/LoanData.zip"

def cleanDf(df):
    df = df.drop(['ReportAsOfEOD', 'ListedOnUTC', 'BidsPortfolioManager', 'BiddingStartedOn', 'BidsApi', 'BidsManual',
             'LoanApplicationStartedDate',
             'ApplicationSignedHour', 'ApplicationSignedWeekday', 'Rating_V0', 'Rating_V1', 'Rating_V2'], axis=1)
    df = df[pd.notnull(df['Rating'])]
    #df.loc[:, 'LoanDate'] = pd.to_datetime(df['LoanDate'])
    #df.loc[:, 'DefaultDate'] = pd.to_datetime(df['DefaultDate'])
    #df.loc[:, 'ContractEndDate'] = pd.to_datetime(df['ContractEndDate'])
    return df

def extractNeededColumns(df):
    df = df[['Rating', 'ProbabilityOfDefault', 'Country', 'LoanDate', 'LoanDuration', 'DefaultDate', 'ContractEndDate']]
    df = df[df['Country'] != 'SK']
    df['ttd'] = df.DefaultDate.dt.to_period('M') - df.LoanDate.dt.to_period('M')
    df.ttd = df.ttd.astype('int')
    df['ttce'] = df.ContractEndDate.dt.to_period('M') - df.LoanDate.dt.to_period('M')
    df.ttce = df.ttce.astype('int')
    df['ttn'] = now # - datetime.timedelta(days=12)
    df.ttn = df.ttn.apply(pd.to_datetime)
    df['ttn'] = df.ttn.dt.to_period('M') - df.LoanDate.dt.to_period('M')
    df.ttn = df.ttn.astype('int')
    df = df[df.ttn >= 3]
    df['tt'] = np.where(df.ttce >= 0, np.where(df.ttn < df.ttce, df.ttn, df.ttce), df.ttn)
    return  df

def printProbabilities(df, country, start_year, duration=60, ratings=('AA', 'A', 'B', 'C', 'D', 'E', 'F', 'HR')):
    grouped3 = df[(df['LoanDate'].dt.year >= start_year) & (df['Rating'].isin(ratings)) &(df['Country'] == country) & (df['LoanDuration'] <= duration)]['ProbabilityOfDefault'].groupby(
        [df['Rating'], df['LoanDate'].dt.year])
    # grouped4 = df[df['LoanDate'].dt.year > 2015]['ProbabilityOfDefault'].groupby(
    #     [df['Rating'], df['Country'], df['LoanDate'].dt.year, df['LoanDuration']])
    # grouped4.agg(['min', 'median', 'mean', 'max', 'std'])
    k = grouped3.agg(['min', 'median', 'mean', 'max', 'std'])
    k.columns.name = 'ProbabilityOfDefault'
    new_idx = k.index.set_levels(['AA', 'A', 'B', 'C', 'D', 'E', 'F', 'HR'], 0)
    k = k.reindex(new_idx)
    with pd.option_context('display.max_rows', None, 'display.max_columns', None): print(k)

def calculateBuckets(df, country, start_year):
    # Let's tackle Estonia first
    grp_ee = df[(df['LoanDate'].dt.year >= start_year) & (df['Country'] == country) & (df.ttd != -9223372036854775808)][
        'ProbabilityOfDefault'].groupby([df['ttd'], df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']])
    grp_ee_dflt = grp_ee.count()
    defaulted_maturities = grp_ee_dflt.index.get_level_values(0)

    grp_ee_surv = df[(df['LoanDate'].dt.year >= start_year) & (df['Country'] == country) & (df.ttd == -9223372036854775808)][
        'ProbabilityOfDefault'].groupby([df['tt'], df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']])
    grp_ee_surv_cnt = grp_ee_surv.count()
    maturities = list(set(grp_ee_surv_cnt.index.get_level_values(0)))
    ee_surv = []
    ee_default_probs = []
    ee_counts = df[(df['LoanDate'].dt.year >= start_year) & (df['Country'] == country)][
        'ProbabilityOfDefault'].groupby([ df['Rating'], df['LoanDate'].dt.year, df['LoanDuration']]).count()
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

    annual_dflt_intensity = pd.concat([annual_dflt_intensity, ee_counts], axis = 1)
    annual_dflt_intensity.columns = ['Annual Default Intensity', '#']

    new_idx = annual_dflt_intensity.index.set_levels(['AA', 'A', 'B', 'C', 'D', 'E', 'F', 'HR'], 0)
    annual_dflt_intensity = annual_dflt_intensity.reindex(new_idx)
    annual_dflt_intensity['#'] = annual_dflt_intensity['#'].fillna(0).astype('int')
    return  annual_dflt_intensity

def default_incidence(s):
    num_defaulted = s[s == False].count()
    total_num = s.count()
    return num_defaulted / total_num, num_defaulted, total_num

def check_probability_of_default(df, country):
    categories = pd.cut(df[(df.Country == country)].ProbabilityOfDefault, [x / 1000. for x in range(0, 1001, 25)])
    grouped = df[(df.Country == country)]['DefaultDate'].isnull().groupby(
        [categories, df['Rating'], df['LoanDate'].dt.year])
    k = grouped.agg(default_incidence)
    k.name = 'ProbabilityOfDefaultAccuracy'
    new_idx = k.index.set_levels(['AA', 'A', 'B', 'C', 'D', 'E', 'F', 'HR'], 1)
    k = k.reindex(new_idx)
    with pd.option_context('display.max_rows', None, 'display.max_columns', None): print(k)

with requests.get(BONDORA_URL) as s:
    df = pd.read_csv(io.BytesIO(s.content), index_col=['LoanId'],
                     infer_datetime_format=True, parse_dates=['LoanDate', 'DefaultDate', 'ContractEndDate'],
                     compression='zip')

# df = pd.read_csv('~/Downloads/LoanData-3.csv', index_col=['LoanId'],
#                  infer_datetime_format=True, parse_dates=['LoanDate', 'DefaultDate', 'ContractEndDate'])
df = cleanDf(df)
df = extractNeededColumns(df)
printProbabilities(df, 'EE', 2015)
ee = calculateBuckets(df, 'EE', 2015)
fi = calculateBuckets(df, 'FI', 2015)

ee.loc[(['AA','A','B'], [2017,2018]), :]
ee['Annual Default Intensity'].loc['AA':'B', 2017:2018]

df2 = pd.read_excel('/Users/ilchen/Downloads/InvestmentsListV2_20180817234017.xlsx',
                    infer_datetime_format=True, parse_dates=['LoanDate', 'DefaultDate', 'ContractEndDate'])
df2 = df2.set_index('LoanId')
df2 = df2[~df2.index.duplicated(keep='first')]
idx = df.index.intersection(df2.index.unique().map(lambda x: x.upper()))

df2 = df.loc[idx]

categories = pd.cut(df2[(df2.Country == 'EE')].ProbabilityOfDefault, [x / 1000. for x in range(0, 1001, 25)])
grouped = df2[(df2.Country == 'EE')].groupby([categories, df['Rating'], df['LoanDate'].dt.year])
df2[(df2.Country == 'EE')]['DefaultDate'].isnull()
#df2[(df2.ProbabilityOfDefault > .1) & (df2.ttd != -9223372036854775808) & (df['Rating'] == 'AA')],\
#    [0., .025, .05, .075, .1, .125, .15, .175, .2, .225, .25, .275]
grouped = df2[(df2.Country == 'EE')]['DefaultDate'].isnull().groupby([categories, df['Rating'], df['LoanDate'].dt.year])



