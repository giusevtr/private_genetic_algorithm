import itertools

import jax.random
import matplotlib.pyplot as plt
import pandas as pd
import os
from models import GSD, SimpleGAforSyncData, PrivGAJit
from stats import ChainedStatistics, Marginals
# from utils.utils_data import get_data
from utils import timer
import jax.numpy as jnp
# from dp_data.data import get_data
from utils import timer, Dataset, Domain , get_Xy, filter_outliers
import seaborn as sns
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.linear_model import LogisticRegression

from dp_data import load_domain_config, load_df

from dev.dataloading.data_functions.acs import get_acs_all


def run(dataset_name,  seeds=(0, 1, 2), eps_values=(0.07, 0.23, 0.52, 0.74, 1.0),
        evaluate_only=False):
    module_name = '2-Mixed BT'
    Res = []

    root_path = '../../dp-data-dev/datasets/preprocessed/folktables/1-Year/'
    config = load_domain_config(dataset_name, root_path=root_path)
    df_train = load_df(dataset_name, root_path=root_path, idxs_path='seed0/train')
    df_test = load_df(dataset_name, root_path=root_path, idxs_path='seed0/test')

    print(f'train size: {df_train.shape}')
    print(f'test size:  {df_test.shape}')
    domain = Domain.fromdict(config)
    data = Dataset(df_train, domain)

    # Create statistics and evaluate
    # module0 = MarginalsDiff.get_all_kway_categorical_combinations(data.domain, k=2)

    module = Marginals.get_all_kway_mixed_combinations_v1(domain, k=2, bins=[2, 4, 8, 16, 32])
    stat_module = ChainedStatistics([module])
    stat_module.fit(data)
    true_stats = stat_module.get_all_true_statistics()
    stat_fn = stat_module.get_dataset_statistics_fn()

    print(f'{dataset_name} has {len(domain.get_numeric_cols())} real features and '
          f'{len(domain.get_categorical_cols())} cat features.')
    print(f'Data cardinality is {domain.size()}.')
    print(f'Number of queries is {true_stats.shape[0]}.')

    algo = GSD(num_generations=200000,
               domain=domain, data_size=2000, population_size=100, muta_rate=1, mate_rate=1,
               print_progress=True)

    delta = 1.0 / len(data) ** 2
    for seed in seeds:
        for eps in eps_values:
            key = jax.random.key(seed)
            t0 = timer()
            sync_dir = f'sync_data/{dataset_name}/GSD/{module_name}/oneshot/oneshot/{eps:.2f}/'
            os.makedirs(sync_dir, exist_ok=True)
            sync_data_path = f'{sync_dir}/sync_data_{seed}.csv'
            if evaluate_only:
                df = pd.read_csv(sync_data_path)
                sync_data = Dataset(df, domain)
            else:
                sync_data = algo.fit_dp(key, stat_module=stat_module,
                                           epsilon=eps, delta=delta,
                                           )
                # sync_data.df.to_csv(sync_data_path, index=False)

            errors = jnp.abs(true_stats - stat_fn(sync_data))
            elapsed_time = timer() - t0
            print(f'GSD({dataset_name, module_name}): eps={eps:.2f}, seed={seed}'
                  f'\t max error = {errors.max():.5f}'
                  f'\t avg error = {errors.mean():.5f}'
                  f'\t time = {elapsed_time:.4f}')
            Res.append(['GSD', dataset_name, module_name, "oneshot", "oneshot", eps, seed, 'Max', errors.max(), elapsed_time])
            Res.append(['GSD', dataset_name, module_name, "oneshot", "oneshot", eps, seed, 'Average', errors.mean(), elapsed_time])

        print()

    columns = ['Generator', 'Data', 'Statistics', 'T', 'S', 'epsilon', 'seed', 'error type', 'error', 'time']
    results_df = pd.DataFrame(Res, columns=columns)
    return results_df

if __name__ == "__main__":

    DATA = [
        # 'folktables_2018_coverage_CA',
        # 'folktables_2018_employment_CA',
        # 'folktables_2018_income_CA',
        # 'folktables_2018_mobility_CA',
        'folktables_2018_travel_CA',
    ]

    os.makedirs('icml_results/', exist_ok=True)
    file_name = 'icml_results/gsd_oneshot_2Mixed_BT.csv'
    results = None
    if os.path.exists(file_name):
        print(f'reading {file_name}')
        results = pd.read_csv(file_name)
    for data in DATA:
        results_temp = run(data,
                           # eps_values=[1.0, 0.74, 0.52, 0.23, 0.07],
                           eps_values=[1],
                           seeds=[0],
                           evaluate_only=False)
        results = pd.concat([results, results_temp], ignore_index=True) if results is not None else results_temp
        print(f'Saving: {file_name}')
        # results.to_csv(file_name, index=False)

