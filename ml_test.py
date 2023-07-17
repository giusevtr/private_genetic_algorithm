import itertools
import os, sys
import jax.random
import pandas as pd
import numpy as np
from models import GeneticSDConsistent as GeneticSD
from models import GSD
from stats import ChainedStatistics,  Marginals, NullCounts
import jax.numpy as jnp
from dp_data import load_domain_config, load_df
from eval_ml import  get_Xy, get_evaluate_ml
from dp_data.data_preprocessor import DataPreprocessor
from utils import timer, Dataset, Domain
import sklearn
import seaborn as sns
import matplotlib.pyplot as plt

from sklearn.metrics import make_scorer, f1_score, roc_auc_score, average_precision_score, accuracy_score
cat_only = False
eps = 100000
# data_size_str = '32000'
COLUMNS = [
    'Model', 'target', 'Eval Data', 'Metric', 'Score', 'Sub Score', 'Data', 'Type', 'N', 'Categorical Only', 'Seed'
]
data_size_str_list = ['2000', '4000', '8000', '16000', '32000']
k = 3
SEEDS = [0]
QUANTILES = 30
DATA = [
    ('folktables_2018_coverage_CA', 'PUBCOV'),
    ('folktables_2018_mobility_CA', 'MIG'),
    ('folktables_2018_employment_CA', 'ESR'),
    ('folktables_2018_income_CA', 'PINCP'),
    ('folktables_2018_travel_CA', 'JWMNP'),
]

Results = []
for (dataset_name, target), seed, cat_only in itertools.product(DATA, SEEDS, [True, False]):
    root_path = 'dp-data-dev/datasets/preprocessed/folktables/1-Year/'
    config = load_domain_config(dataset_name, root_path=root_path)
    domain = Domain(config=config)
    df_train = load_df(dataset_name, root_path=root_path, idxs_path=f'seed{seed}/train')
    df_test = load_df(dataset_name, root_path=root_path, idxs_path=f'seed{seed}/test')

    if cat_only:
        cat_cols = domain.get_categorical_cols() + domain.get_ordinal_cols()
        domain = domain.project(cat_cols)

    eval_ml = get_evaluate_ml(
        domain=domain,
        targets=[target],
        models=['LogisticRegression', 'RandomForest', 'XGBoost', 'LightGBM',],
        grid_search=False
    )

    print(f'DATA={dataset_name}')
    y_test = df_test[target].values
    cons_pred_acc = max(accuracy_score(y_true=y_test, y_pred=np.zeros_like(y_test)),
                        accuracy_score(y_true=y_test, y_pred=np.ones_like(y_test)))
    temp_acc = ['Constant', target, 'Test', 'accuracy', cons_pred_acc, None, dataset_name, 'Original', 'N', cat_only, seed]

    cons_pred_f1 = max(f1_score(y_true=y_test, y_pred=np.zeros_like(y_test), average='macro'),
                       f1_score(y_true=y_test, y_pred=np.ones_like(y_test), average='macro'))
    temp_f1 = ['Constant', target, 'Test', 'f1_macro', cons_pred_f1, None, dataset_name, 'Original', 'N', cat_only, seed]

    Results.append(pd.DataFrame([temp_f1, temp_acc], columns=COLUMNS))

    print(f'Constant predictor = {cons_pred_acc}')
    for data_size_str in data_size_str_list:
        print(f'Data size = ', data_size_str)
        print('Cat only ? ', cat_only)
        data_size = int(data_size_str)
        sync_dir = f'sync_data/{dataset_name}/{k}/{eps:.2f}/{data_size_str}/oneshot'
        sync_path = f'{sync_dir}/sync_data_{seed}.csv'
        print(sync_path)
        df_sync = pd.read_csv(sync_path)
        features = df_sync.columns

        metric_name = 'accuracy'
        print('SYNC:')
        sync_results_df = eval_ml(df_sync, df_test, seed, group=None)
        print(sync_results_df)

        sync_results_df['Data'] = dataset_name
        sync_results_df['Type'] = 'Sync'
        sync_results_df['N'] = data_size_str
        sync_results_df['Categorical Only'] = cat_only
        sync_results_df['Seed'] = seed
        Results.append(sync_results_df)


results_df = pd.concat(Results)
results_df.to_csv('acs_sync_ml_results.csv', index=False)

