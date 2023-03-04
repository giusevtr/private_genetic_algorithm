import jax.random
from models import GeneticSD, GeneticStrategy

from stats import Marginals, ChainedStatistics
from utils.utils_data import get_data
from utils import timer
import jax.numpy as jnp

if __name__ == "__main__":

    # data_name = f'folktables_2018_CA'
    data_name = 'folktables_2018_mobility_CA'
    data = get_data(f'{data_name}-mixed-train', domain_name=f'domain/{data_name}-mixed', root_path='../../data_files/folktables_datasets')
    # data = get_classification(DATA_SIZE=1000)
    print(f'Dataset: {data_name}')

    # Create statistics and evaluate
    marginal_module2 = Marginals.get_all_kway_combinations(data.domain, k=2, bins=[2, 4, 8, 16, 32])

    stat_module = ChainedStatistics([
                                         marginal_module2,
                                         ])
    stat_module.fit(data)

    true_stats = stat_module.get_all_true_statistics()
    stat_fn = stat_module._get_workload_fn()

    # Choose algorithm parameters
    SYNC_DATA_SIZE = 2000
    algo = GeneticSD(num_generations=20000,
                     print_progress=False,
                     strategy=GeneticStrategy(domain=data.domain, elite_size=5, data_size=SYNC_DATA_SIZE))

    delta = 1.0 / len(data) ** 2
    # Generate differentially private synthetic data with ADAPTIVE mechanism
    for eps in [0.07]:
    # for eps in [0.07, 0.23, 0.52, 0.74, 1.0]:
        # for seed in [0, 1, 2]:
        for seed in [0]:
            key = jax.random.PRNGKey(seed)
            t0 = timer()
            sync_data = algo.fit_dp_adaptive(key, stat_module=stat_module, epsilon=eps, delta=delta, rounds=20)
            sync_data.df.to_csv(f'{data_name}_sync_{eps:.2f}_{seed}.csv', index=False)
            errors = jnp.abs(true_stats - stat_fn(sync_data.to_numpy()))
            print(f'PrivGA: eps={eps:.2f}, seed={seed}'
                  f'\t max error = {errors.max():.5f}'
                  f'\t avg error = {errors.mean():.5f}'
                  f'\t time = {timer() - t0:.4f}')

            noisy_stats = stat_module.get_selected_noised_statistics()
            sel_true_stats = stat_module.get_selected_statistics_without_noise()
            gau_errors = jnp.abs(sel_true_stats - noisy_stats)
            print(  f'\t Gau max error = {gau_errors.max():.5f}')
            # plot_2d_data(sync_data.to_numpy())

        print()

