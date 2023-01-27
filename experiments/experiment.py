import itertools
import folktables
import numpy as np
import pandas as pd
from folktables import ACSDataSource, ACSEmployment
from utils import Dataset, Domain, DataTransformer
from models import Generator, PrivGA, SimpleGAforSyncData, RelaxedProjection
from stats import Marginals
from utils.utils_data import get_data
import os
import jax
import jax.numpy as jnp


"""
Runtime analysis of PrivGA
Split the ACS datasets. 
RAP datasize = 50000
3-way marginals
3 random seeds
T= [25, 50, 100]
"""

tasks = ['mobility']
states = ['CA']
# tasks = ['employment', 'coverage', 'income', 'mobility', 'travel']
# states = ['NY', 'CA', 'FL', 'TX', 'PA']
EPSILON = (0.07, 0.23, 0.52, 0.74, 1.0)

def run_experiments(data: Dataset,
                    algorithm: Generator,
                    stats_module: Marginals,
                    data_name,
                    epsilon=(0.07, 0.15, 0.23, 0.41, 0.52, 0.62, 0.74, 0.87, 1.0),
                    adaptive_rounds=(25, 50, 100),
                    seeds=(0, 1, 2),
                    save_dir: tuple = ('real_valued_sync_data',),
                    data_post_processing=lambda x: x,num_samples=1):

    num_workloads = len(stats_module.true_stats)
    N = data.df.shape[0]
    RESULTS=[]
    for T, eps, seed in itertools.product(list(adaptive_rounds), list(epsilon), list(seeds)):
        # if num_workloads < T:
        #     print(f'Skipping (T={T}, eps={eps:2f}, seed={seed}. {str(algorithm)}) because number '
        #           f'of workloads {len(stats_module.true_stats)} is smaller than T={T}')
        #     continue
        delta = 1/N**2
        key = jax.random.PRNGKey(seed)
        sync_data = algorithm.fit_dp_adaptive(key, stat_module=stats_module, start_sync=True,
                                              rounds=T, epsilon=eps, delta=delta, print_progress=True,num_sample=num_samples)

        true_stats = stats_module.get_true_stats()
        errors = true_stats - stats_module.get_stats(sync_data)
        max_error = jnp.abs(errors).max()
        ave_error = jnp.linalg.norm(errors, ord=1)/true_stats.shape[0]
        RESULTS.append(
            [data_name, str(algorithm), str(stats_module), T, eps, seed, max_error, ave_error])
        print(f'T={T}, eps={eps:2f}, seed={seed}. {str(algorithm)}:\tmax error = {max_error:.5f}, ave error = {ave_error:.7f}')

        # Post process before saving
        sync_data_post = data_post_processing(sync_data)


        save_dir = list(save_dir)
        save_path = ''
        # save_path = save_dir
        for s in save_dir:
            save_path = os.path.join(save_path, s)
            os.makedirs(s, exist_ok=True)
        save_path = os.path.join(save_path, f'{T:03}')
        os.makedirs(save_path, exist_ok=True)
        save_path = os.path.join(save_path, f'{eps:.2f}')
        os.makedirs(save_path, exist_ok=True)
        save_path = os.path.join(save_path, f'sync_data_{seed}.csv')
        data_df: pd.DataFrame = sync_data_post.df
        print(f'Saving {save_path}')
        data_df.to_csv(save_path)

        print()
    results_df = pd.DataFrame(RESULTS,
                              columns=['data', 'generator', 'stats', 'T', 'epsilon', 'seed', 'max error', 'l1 error'])
    save_path = ''
    for s in save_dir:
        save_path = os.path.join(save_path, s)
        os.makedirs(s, exist_ok=True)
    save_path = os.path.join(save_path,f"result_{seeds[0]}.csv")
    results_df.to_csv(save_path)

if __name__ == "__main__":
    # df = folktables.

    # tasks = ['employment', 'coverage', 'income', 'mobility', 'travel']
    tasks = [ 'mobility', 'travel']
    states = ['CA']

    for task, state in itertools.product(tasks, states):
        data_name = f'folktables_2018_{task}_{state}'
        data = get_data(f'folktables_datasets/{data_name}-mixed-train',
                        domain_name=f'folktables_datasets/domain/{data_name}-mixed')

        # stats_module = TwoWayPrefix.get_stat_module(data.domain, num_rand_queries=1000000)
        stats_module = Marginals.get_all_kway_mixed_combinations(data.domain, 3, bins=[2, 4, 8, 16, 32])

        stats_module.fit(data)
        privga = PrivGA(
            num_generations=20000,
            stop_loss_time_window=100,
            print_progress=False,
            strategy=SimpleGAforSyncData(domain=data.domain,
                                         population_size=50,
                                         elite_size=2,
                                         data_size=200,
                                         muta_rate=1,
                                         mate_rate=10))

        run_experiments(data=data,  algorithm=privga, stats_module=stats_module, epsilon=EPSILON,
                        save_dir=('real_valued_sync_data', data_name, 'PrivGA'))

        #######
        ## RAP
        #######
        data_disc = data.discretize(num_bins=32)
        train_stats_module = Marginals.get_all_kway_combinations(data_disc.domain, 3)
        train_stats_module.fit(data_disc)

        numeric_features = data.domain.get_numeric_cols()
        rap_post_processing = lambda data: Dataset.to_numeric(data, numeric_features)


        rap = RelaxedProjection(domain=data_disc.domain, data_size=500, iterations=5000, learning_rate=0.01,
                                print_progress=False)
        run_experiments(data=data_disc,  algorithm=rap, stats_module=stats_module, epsilon=EPSILON,
                        save_dir=('real_valued_sync_data', data_name, 'RAP'),
                        data_post_processing=rap_post_processing)

