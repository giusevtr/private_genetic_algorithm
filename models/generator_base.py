import jax
# from stats import PrivateStatistic
from stats import Marginals, PrivateMarginalsState
import time
from utils import Dataset, Domain
from utils.cdp2adp import cdp_rho
import numpy as np
import jax.numpy as jnp
import pandas as pd
from typing import Callable


class Generator:
    data_size: int
    early_stop_elapsed_time = 5
    last_time: float = None
    last_error: float = None

    def early_stop_init(self):
        self.last_time: float = time.time()
        self.last_error = 10000000
        self.start_time = time.time()

    def early_stop(self, error):
        current_time = time.time()
        stop_early = False
        if current_time - self.last_time > self.early_stop_elapsed_time:
            loss_change = jnp.abs(error - self.last_error) / self.last_error
            if loss_change < 0.001:
                stop_early = True
            self.last_time = current_time
            self.last_error = error
        return stop_early




    def fit(self, key: jax.random.PRNGKeyArray, stat_module: PrivateMarginalsState, init_X=None, tolerance:float=0) -> Dataset:
        pass

    # @staticmethod
    # def default_debug_fn(X):
    def fit_dp_adaptive(self, key: jax.random.PRNGKeyArray, stat_module: Marginals, rounds, epsilon, delta, tolerance=0,
                        start_X=False,
                        print_progress=False,
                        debug_fn: Callable = None):
        rho = cdp_rho(epsilon, delta)
        return self.fit_zcdp_adaptive(key, stat_module, rounds, rho, tolerance, start_X, print_progress, debug_fn)

    def fit_zcdp_adaptive(self, key: jax.random.PRNGKeyArray, stat_module: Marginals, rounds, rho, tolerance=0,
                          start_X=False,
                             print_progress=False,
                          debug_fn: Callable = None):
        rho_per_round = rho / rounds
        domain = stat_module.domain

        key, key_init = jax.random.split(key, 2)
        X_sync = Dataset.synthetic_jax_rng(domain, N=self.data_size, rng=key_init)
        # data_init = Dataset.synthetic(domain, N=self.data_size, rng=key_init)
        sync_dataset = None


        # true_answers = prefix_fn(data.to_numpy())

        ADA_DATA = {'epoch': [],
                    'average error': [],
                    'max error': [],
                    'round true max error': [],
                    'round true avg error': [],
                    'round priv max error': [],
                    'round priv avg error': [],
                    'time': [],
                    }

        true_stats = stat_module.get_true_stats()

        stat_state = PrivateMarginalsState()
        for i in range(1, rounds + 1):
            stime = time.time()

            # Select a query with max error using the exponential mechanism and evaluate
            key, subkey_select = jax.random.split(key, 2)
            stat_state = stat_module.private_select_measure_statistic(subkey_select, rho_per_round, X_sync, stat_state)
            # state = stat_module.priv_update(subkey_select, state, rho_per_round, X_sync)


            key, key_fit = jax.random.split(key, 2)
            dataset: Dataset
            if start_X:
                sync_dataset = self.fit(key_fit, stat_state, X_sync, tolerance=tolerance)
            else:
                sync_dataset = self.fit(key_fit, stat_state, tolerance=tolerance)

            ##### PROJECT STEP
            X_sync = sync_dataset.to_numpy()

            # Get errors for debugging
            errors_post_max = stat_module.get_sync_data_errors(X_sync).max()
            errors_post_avg = jnp.linalg.norm(true_stats - stat_module.get_stats_jit(sync_dataset), ord=1)/true_stats.shape[0]

            round_true_max_loss = stat_state.true_loss_inf(X_sync)
            round_true_ave_loss = stat_state.true_loss_l2(X_sync)

            round_priv_max_loss = stat_state.true_loss_inf(X_sync)
            round_priv_ave_loss = stat_state.true_loss_l2(X_sync)

            if print_progress:
                gaussian_error = jnp.abs(stat_state.get_priv_stats() - stat_state.get_true_stats()).max()
                print(f'Epoch {i:03}: Total error(max/avg) is {errors_post_max:.4f}/{errors_post_avg:.7f}.\t ||'
                      f'\tRound: True error(max/l2) is {stat_state.true_loss_inf(X_sync):.5f}/{stat_state.true_loss_l2(X_sync):.7f}.'
                      # f'\t(true) max error = {stat_state.true_loss_inf(X_sync):.4f}.'
                      # f'\t(true)  l2 error = {stat_state.true_loss_l2(X_sync):.5f}.'
                      f'\tPriv error(max/l2) is {stat_state.priv_loss_inf(X_sync):.5f}/{stat_state.priv_loss_l2(X_sync):.7f}.'
                      f'\tGaussian max error {gaussian_error:.6f}.'
                      f'\tElapsed time = {time.time() - stime:.4f}s')
            if debug_fn is not None:
                debug_fn(i, sync_dataset)
            ADA_DATA['epoch'].append(i)
            ADA_DATA['max error'].append(float(errors_post_max))
            ADA_DATA['average error'].append(float(errors_post_avg))
            ADA_DATA['round true max error'].append(float(round_true_max_loss))
            ADA_DATA['round true avg error'].append(float(round_true_ave_loss))
            ADA_DATA['round priv max error'].append(float(round_priv_max_loss))
            ADA_DATA['round priv avg error'].append(float(round_priv_ave_loss))
            ADA_DATA['time'].append(float(time.time() - stime))
            # ADA_DATA['round init error'].append(initial_max_error)

        df = pd.DataFrame(ADA_DATA)
        df['algo'] = str(self)
        df['rho'] = rho
        df['rounds'] = rounds
        self.ADA_DATA = df
        return sync_dataset

def exponential_mechanism(key:jnp.ndarray, scores: jnp.ndarray, eps0: float, sensitivity: float):
    dist = jax.nn.softmax(2 * eps0 * scores / (2 * sensitivity))
    cumulative_dist = jnp.cumsum(dist)
    max_query_idx = jnp.searchsorted(cumulative_dist, jax.random.uniform(key, shape=(1,)))
    return max_query_idx[0]

