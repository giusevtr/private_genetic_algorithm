import itertools

import jax.random
import matplotlib.pyplot as plt
import pandas as pd
import os
from models import GSD
from stats import ChainedStatistics, Marginals
import jax.numpy as jnp
from utils import timer, Dataset, Domain
from dp_data import load_domain_config, load_df


def run(dataset_name,  seeds=(0, 1, 2), eps_values=(0.07, 0.23, 0.52, 0.74, 1.0)):
    module_name = '2Cat'
    Res = []

    root_path = '../../dp-data-dev/datasets/preprocessed/folktables/1-Year/'
    config = load_domain_config(dataset_name, root_path=root_path)
    df_train = load_df(dataset_name, root_path=root_path, idxs_path='seed0/train')
    df_test = load_df(dataset_name, root_path=root_path, idxs_path='seed0/test')

    print(f'train size: {df_train.shape}')
    print(f'test size:  {df_test.shape}')
    domain = Domain.fromdict(config)
    data = Dataset(df_train, domain)

    module = Marginals.get_kway_categorical(domain, k=2)
    stat_module = ChainedStatistics([module])
    stat_module.fit(data)
    true_stats = stat_module.get_all_true_statistics()
    stat_fn = stat_module.get_dataset_statistics_fn()

    print(f'{dataset_name} has {len(domain.get_numeric_cols())} real features and '
          f'{len(domain.get_categorical_cols())} cat features.')
    print(f'Data cardinality is {domain.size()}.')
    print(f'Number of queries is {true_stats.shape[0]}.')

    algo = GSD(num_generations=2000000,
               domain=domain,
               data_size=32000,
               population_size=100,
               print_progress=False)

    delta = 1.0 / len(data) ** 2
    for seed in seeds:
        for eps in eps_values:
            key = jax.random.key(seed)
            t0 = timer()
            sync_dir = f'sync_data/{dataset_name}/GSD/{module_name}/oneshot/oneshot/{eps:.2f}/'
            os.makedirs(sync_dir, exist_ok=True)
            sync_data = algo.fit_dp(key, stat_module=stat_module,epsilon=eps, delta=delta,)
            save_path = f'{sync_dir}/sync_data_{seed}.csv'
            print(f'Saving {save_path}')
            sync_data.df.to_csv(save_path, index=False)
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

    os.makedirs('icml_results/oneshot_categorical', exist_ok=True)
    file_name = 'icml_results/oneshot_categorical/gsd_oneshot_categorical.csv'
    results = None
    for data in DATA:
        results_temp = run(data, eps_values=[1000], seeds=[0])
        results = pd.concat([results, results_temp], ignore_index=True) if results is not None else results_temp
        print(f'Saving: {file_name}')
        results.to_csv(file_name, index=False)

