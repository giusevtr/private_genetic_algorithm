import jax.numpy as jnp
import numpy as np
import pandas as pd
from models import Generator
import time
from stats import ChainedStatistics
import jax
import chex
from flax import struct
from utils import Dataset, Domain, timer
from functools import partial
from typing import Tuple
import random


@struct.dataclass
class EvoState:
    archive: chex.Array
    fitness: chex.Array
    best_member: chex.Array
    best_fitness: float = jnp.finfo(jnp.float64).max


@struct.dataclass
class PopulationState:
    # X: chex.Array
    row_id: chex.Array
    remove_row: chex.Array
    add_row: chex.Array


def get_best_fitness_member(
    x: chex.Array, fitness: chex.Array, state
) -> Tuple[chex.Array, chex.Array, chex.Array, chex.Array]:
    best_in_gen = jnp.argmin(fitness)
    best_in_gen_fitness, best_in_gen_member = (
        fitness[best_in_gen],
        x[best_in_gen],
    )
    replace_best = best_in_gen_fitness < state.best_fitness
    best_fitness = jax.lax.select(
        replace_best, best_in_gen_fitness, state.best_fitness
    )
    best_member = jax.lax.select(
        replace_best, best_in_gen_member, state.best_member
    )
    return best_member, best_fitness, replace_best, best_in_gen


class SDStrategy:
    def __init__(self, domain: Domain,
                 data_size: int,
                 population_size_muta: int = 50,
                 population_size_cross: int = 50,
                 population_size: int = None,
                 elite_size: int = 5,
                 muta_rate: int = 1,
                 mate_rate: int = 1,
                 debugging=False):
        """Simple Genetic Algorithm For Synthetic Data Search Adapted from (Such et al., 2017)
        Reference: https://arxiv.org/abs/1712.06567
        Inspired by: https://github.com/hardmaru/estool/blob/master/es.py"""

        if population_size is not None:
            self.population_size_muta = population_size // 2
            self.population_size_cross = population_size // 2
        else:
            self.population_size_muta = population_size_muta
            self.population_size_cross = population_size_cross
        self.population_size = self.population_size_muta + self.population_size_cross
        self.elite_size = elite_size
        self.data_size = data_size

        self.domain = domain
        self.num_devices = jax.device_count()
        self.domain = domain

        # It's recommended to always set  muta_rate=muta_rate=1
        assert muta_rate > 0, "Mutation rate must be greater than zero."
        assert mate_rate > 0, "Mate rate must be greater than zero."
        assert muta_rate == mate_rate, "Mutations and crossover must be the same."
        self.muta_rate = muta_rate
        self.mate_rate = mate_rate
        self.debugging = debugging

    def initialize(
            self, rng: chex.PRNGKey
    ) -> EvoState:
        """`initialize` the evolution strategy."""
        init_x = self.initialize_elite_population(rng)
        state = EvoState(
            archive=init_x.astype(jnp.float64),
            fitness=jnp.zeros(self.elite_size) + jnp.finfo(jnp.float64).max,
            best_member=init_x[0].astype(jnp.float64),
            best_fitness=jnp.finfo(jnp.float64).max
        )
        self.update_candidate_vmap = jax.vmap(update_candidate, in_axes=(None, 0, 0))

        rng1, rng2 = jax.random.split(rng, 2)
        random_numbers = jax.random.permutation(rng1, self.data_size, independent=True)
        muta_fn = get_mutate_fn()
        mate_fn = get_mating_fn(self.domain)

        self.muta_vmap = jax.jit(jax.vmap(muta_fn, in_axes=(None, 0, 0, 0)))
        self.mate_vmap = jax.jit(jax.vmap(mate_fn, in_axes=(None, 0)))
        self.samplers = [jax.jit(self.domain.get_sampler(col, self.population_size_muta)) for col in self.domain.attrs]
        self.column_ids = self.domain.sample_columns_based_on_logsize() # Mutate columns based on their cardinality
        self.sample_id = 0

        self.sampler_time = 0
        self.ask_time = 0
        self.g = 0
        return state

    @partial(jax.jit, static_argnums=(0,))
    def initialize_elite_population(self, rng: chex.PRNGKey):
        d = len(self.domain.attrs)
        pop = Dataset.synthetic_jax_rng(self.domain, self.elite_size * self.data_size, rng)
        initialization = pop.reshape((self.elite_size, self.data_size, d))
        return initialization

    @partial(jax.jit, static_argnums=(0,))
    def initialize_random_population(self, rng: chex.PRNGKey):
        pop = Dataset.synthetic_jax_rng(self.domain, self.population_size, rng)
        return pop

    def ask(self, rng: chex.PRNGKey, state: EvoState):

        t0 = time.time()
        # rng_ask, rng_samples = jax.random.split(rng, 2)
        self.sample_id = (self.sample_id + 1) % len(self.column_ids)
        column = self.column_ids[self.sample_id]
        column_values = self.samplers[column](rng)
        column_values.block_until_ready()
        self.sampler_time += time.time() - t0

        t0 = time.time()
        pop = self.ask_strategy(rng, state, column, column_values)
        pop.remove_row.block_until_ready()
        self.ask_time += time.time() - t0
        return pop


    @partial(jax.jit, static_argnums=(0,))
    def ask_strategy(self, rng_muta: chex.PRNGKey, state: EvoState, i: int, column_values: chex.Array):
        rng_muta, rng_mate = jax.random.split(rng_muta, 2)

        # Mutation
        column_id = (jnp.ones(shape=(self.population_size_muta)) * i).astype(int)
        rng_muta_split = jax.random.split(rng_muta, self.population_size_muta)
        pop_muta = self.muta_vmap(state.best_member, rng_muta_split, column_id, column_values)

        # Crossover
        rng_mate_1, rng_mate_2 = jax.random.split(rng_mate, 2)
        rng_mate_split = jax.random.split(rng_mate_1, self.population_size_cross)
        pop_mate = self.mate_vmap(state.best_member, rng_mate_split)

        population = PopulationState(
            row_id=jnp.concatenate((pop_muta.row_id, pop_mate.row_id)),
            remove_row=jnp.concatenate((pop_muta.remove_row, pop_mate.remove_row), axis=0),
            add_row=jnp.concatenate((pop_muta.add_row, pop_mate.add_row), axis=0))
        return population

    @partial(jax.jit, static_argnums=(0,))
    def update_elite_candidates(self,
            state: EvoState, # best candidate before updates
            population_delta: PopulationState,  # candidate deltas
            fitness: chex.Array):
        X = state.best_member
        idx = jnp.argsort(fitness)[0]
        fitness_elite = fitness[idx].reshape((1,))

        row_idx = population_delta.row_id[idx]
        remove_row = population_delta.remove_row[idx]
        add_row = population_delta.add_row[idx]
        X_elite_upt = update_candidate(X, row_idx, add_row).reshape((1, self.data_size, -1))
        return X_elite_upt, fitness_elite, remove_row, add_row

    @partial(jax.jit, static_argnums=(0,))
    def tell(
            self,
            x: chex.Array, # Candidates before updates
            fitness: chex.Array,
            state: EvoState,
    ) -> Tuple[EvoState, chex.Array, chex.Array]:
        """`tell` performance data for strategy state update."""
        state = self.tell_strategy(x, fitness, state)
        best_member, best_fitness, replace_best, best_in_gen = get_best_fitness_member(x, fitness, state)
        return state.replace(
            best_member=best_member,
            best_fitness=best_fitness,
        ), replace_best, best_in_gen

    def tell_strategy(
            self,
            x: chex.Array,
            fitness: chex.Array,
            state: EvoState,
    ) -> EvoState:
        fitness_concat = jnp.concatenate([state.fitness, fitness])
        idx = jnp.argsort(fitness_concat)[0: self.elite_size]

        solution_concat = jnp.concatenate([state.archive, x])

        new_fitness = fitness_concat[idx]
        new_archive = solution_concat[idx]

        new_state = state.replace(
            fitness=new_fitness, archive=new_archive,
        )

        return new_state


def update_candidate(X, row_id, add_row):
    X_new = X.at[row_id, :].set(add_row[0])
    return X_new


def get_mutate_fn():
    def muta(
            X0,
            rng: chex.PRNGKey,
            mut_col: chex.Array,
            new_col_value: chex.Array
    ) -> PopulationState:
        n, d = X0.shape
        rem_row_idx = jax.random.randint(rng, minval=0, maxval=n, shape=(1,))
        removed_rows_muta = X0[rem_row_idx, :]
        added_rows_muta = removed_rows_muta.at[0, mut_col].set(new_col_value)
        pop_state = PopulationState(row_id=rem_row_idx[0], remove_row=removed_rows_muta, add_row=added_rows_muta)
        return pop_state

    return muta

def get_mating_fn(domain: Domain):
    d = len(domain.attrs)
    numeric_idx = domain.get_attribute_indices(domain.get_numerical_cols()).astype(int)
    mask = jnp.zeros(d)
    mask = mask.at[numeric_idx].set(1)
    mask = mask.reshape((1, d))

    def mate(
            X0, rng: chex.PRNGKey,
    ) -> PopulationState:
        n, d = X0.shape
        rng, rng1, rng2, rng3, rng_normal = jax.random.split(rng, 5)

        rem_row_idx = jax.random.randint(rng1, minval=0, maxval=n, shape=(1,))
        removed_rows_mate = X0[rem_row_idx, :]

        # Copy this row onto the dataset
        add_rows_idx = jax.random.randint(rng2, minval=0, maxval=n, shape=(1,))
        new_rows = X0[add_rows_idx, :]
        upt_col_idx = jax.random.randint(rng3, minval=0, maxval=d, shape=(1,))
        added_rows_mate = removed_rows_mate.at[0, upt_col_idx].set(new_rows[0, upt_col_idx])

        pop_state = PopulationState(row_id=rem_row_idx[0], remove_row=removed_rows_mate, add_row=added_rows_mate)
        return pop_state

    return mate

######################################################################
######################################################################
######################################################################
######################################################################


# @dataclass
class GSD(Generator):

    def __init__(self,
                 num_generations,
                 domain,
                 data_size,
                 population_size_muta=50,
                 population_size_cross=50,
                 population_size=None,
                 muta_rate=1,
                 mate_rate=1,
                 print_progress=False,
                 stop_early=True,
                 stop_early_gen=None,
                 stop_eary_threshold=0,
                 sparse_statistics=False
                 ):
        self.domain = domain
        self.data_size = data_size
        self.num_generations = num_generations
        self.print_progress = print_progress
        self.stop_early = stop_early
        self.stop_eary_threshold = stop_eary_threshold
        self.sparse_statistics = sparse_statistics
        self.stop_early_min_generation = stop_early_gen if stop_early_gen is not None else data_size
        self.strategy = SDStrategy(domain, data_size,
                                   population_size_muta=population_size_muta,
                                   population_size_cross=population_size_cross,
                                   population_size=population_size,
                                   muta_rate=muta_rate, mate_rate=mate_rate)
        self.stop_generation = None

    def __str__(self):
        return f'GSD'

    def fit(self, key, adaptive_statistic: ChainedStatistics,
            sync_dataset: Dataset = None, tolerance: float = 0.0, adaptive_epoch=1):
        """
        Minimize error between real_stats and sync_stats
        """


        if self.sparse_statistics:
            selected_statistics, selected_noised_statistics, statistics_fn = adaptive_statistic.get_selected_trimmed_statistics_fn()
        else:
            selected_noised_statistics = adaptive_statistic.get_selected_noised_statistics()
            selected_statistics = adaptive_statistic.get_selected_statistics_without_noise()
            statistics_fn = adaptive_statistic.get_selected_statistics_fn()

        return self.fit_help(key, selected_noised_statistics, statistics_fn, sync_dataset)

    def fit_help(self, key, selected_noised_statistics, statistics_fn, sync_dataset=None,
                 constraint_fn=None, debug_fn=None):
        self.stop_generation = None
        init_time = timer()

        const_weight = 0.0
        weight_updates = 0
        if constraint_fn is not None:
            constraint_fn_jit = jax.jit(constraint_fn)
            weight_updates = 20
        else:
            constraint_fn = lambda x: 0
            constraint_fn_jit = jax.jit(constraint_fn)

        @jax.jit
        def private_loss(X_arg):
            error = jnp.abs(selected_noised_statistics - statistics_fn(X_arg))
            return jnp.abs(error).max(), jnp.abs(error).mean(), jnp.linalg.norm(error, ord=2)

        def fitness_fn(X, w):
            fitness = jnp.linalg.norm(selected_noised_statistics - statistics_fn(X), ord=2) ** 2
            constraint_score = constraint_fn(X)
            return fitness + w * constraint_score
        fitness_fn_vmap = jax.vmap(fitness_fn, in_axes=(0, None))

        def update_fitness_fn(stats: chex.Array, pop_state: PopulationState, w):
            # 1) Update the statistics of this synthetic dataset
            rem_row = pop_state.remove_row
            add_row = pop_state.add_row
            num_rows = rem_row.shape[0]
            add_stats = (num_rows * statistics_fn(add_row))
            rem_stats = (num_rows * statistics_fn(rem_row))
            upt_sync_stat = stats.reshape(-1) + add_stats - rem_stats

            fitness = jnp.linalg.norm(selected_noised_statistics - upt_sync_stat / self.data_size, ord=2) ** 2
            return fitness

        update_fitness_fn_vmap = jax.vmap(update_fitness_fn, in_axes=(None, 0, None))
        update_fitness_fn_jit = jax.jit(update_fitness_fn_vmap)

        # INITIALIZE STATE
        key, subkey = jax.random.split(key, 2)

        state = self.strategy.initialize(subkey)

        if sync_dataset is not None:
            init_sync = sync_dataset.to_numpy()
            temp = init_sync.reshape((1, init_sync.shape[0], init_sync.shape[1]))
            new_archive = jnp.concatenate([temp, state.archive[1:, :, :]])
            state = state.replace(archive=new_archive)


        elite_fitness = fitness_fn_vmap(state.archive, const_weight)

        best_member_id = elite_fitness.argmin()
        state = state.replace(
            fitness=elite_fitness,
            best_member=state.archive[best_member_id],
            best_fitness=elite_fitness[best_member_id]
        )

        self.early_stop_init()  # Initiate time-based early stop system

        best_fitness_total = 100000
        ask_time = 0
        elite_stat_time = 0
        fit_time = 0
        update_x_time = 0
        tell_time = 0

        elite_stat = self.data_size * statistics_fn(state.best_member)  # Statistics of best SD

        def update_elite_stat(elite_stat_arg,
                              replace_best,
                              remove_row,
                              add_row,
                              ):
            num_rows = remove_row.shape[0]

            new_elite_stat = jax.lax.select(
                    replace_best,
                    elite_stat_arg
                        - (num_rows * statistics_fn(remove_row))
                        + (num_rows * statistics_fn(add_row)),
                    elite_stat_arg
                )
            return new_elite_stat

        update_elite_stat_jit = jax.jit(update_elite_stat)
        LAST_LAG_FITNESS = 1e9
        keys = jax.random.split(key, self.num_generations)
        set_up_time = timer() - init_time
        if self.print_progress:
            print(f'Setup time={set_up_time:.3f}')

        for t, ask_subkey in enumerate(keys):
            self.stop_generation = t  # Update the stop generation

            # ASK
            t0 = time.time()
            population_state = self.strategy.ask(ask_subkey, state)
            population_state.remove_row.block_until_ready()
            ask_time += time.time() - t0

            # FIT
            t0 = timer()
            fitness = update_fitness_fn_jit(elite_stat, population_state, const_weight)
            fitness.block_until_ready()
            fit_time += timer() - t0

            # Update best new candiates
            t0 = time.time()
            best_new_candidates, best_candidate_fitness, remove_row, add_row = self.strategy.update_elite_candidates(state, population_state, fitness)
            remove_row.block_until_ready()
            update_x_time += time.time() - t0

            # TELL
            t0 = timer()
            state, rep_best, best_id = self.strategy.tell(best_new_candidates, best_candidate_fitness, state)
            state.archive.block_until_ready()
            tell_time += timer() - t0

            # UPDATE elite_states
            t0 = timer()
            elite_stat = update_elite_stat_jit(elite_stat,
                                               rep_best,
                                               remove_row,
                                               add_row).block_until_ready()
            elite_stat_time += timer() - t0

            if (t % 10000) == 0:
                self.print_time(t, init_time, set_up_time, ask_time, fit_time, update_x_time, tell_time, elite_stat_time)
                if debug_fn is not None:
                    debug_fn(t, state.best_fitness, Dataset.from_numpy_to_dataset(self.domain, state.best_member))
            if (t % self.stop_early_min_generation) == 0:
                if self.check_early_stop(t, state.best_fitness, LAST_LAG_FITNESS):
                    break
                LAST_LAG_FITNESS = state.best_fitness

        # Save progress for debugging.
        X_sync = state.best_member
        sync_dataset = Dataset.from_numpy_to_dataset(self.domain, X_sync)
        return sync_dataset


    def check_early_stop(self, t, best_fitness, LAST_LAG_FITNESS):
        if (t % self.stop_early_min_generation) > 0: return False
        if (t <= self.stop_early_min_generation): return False
        if not self.stop_early or t == 0: return False
        loss_change = jnp.abs(LAST_LAG_FITNESS - best_fitness) / LAST_LAG_FITNESS
        #
        if loss_change < 0.0001:
            if self.print_progress:
                print(f'\t\t ### Stop early at {t} ###')
            return True
        return False
            # constraint_loss = constraint_fn_jit(state.best_member)
            # constraint_loss.block_unitl_ready()
            # if weight_updates > 0 and constraint_loss > 0:
            #     const_weight = 2 * const_weight + 0.1  # Increase weight assigned to constraints
            #     state = state.replace(best_fitness=1e9)  # For the algorithm to update the next generation
            #     weight_updates = weight_updates - 1
            #     if self.print_progress:
            #         print(f'\tGen {t:<3}: Increasing weight({weight_updates:<3}): w={const_weight:.5f}.'
            #               f' Constraint loss={constraint_loss:.5f}')
            # else:
            #     if self.print_progress:
            #         print(f'\t\t ### Stop early at {t} ###')
            #     break
    def print_time(self, t, init_time, set_up_time, ask_time, fit_time, upt_x_time, tell_time, elite_stat_time):
        elapsed_time = timer() - init_time
        print(f'\tGen {t:05},  ', end=' ')
        print(f'\t|time={elapsed_time:.5f}(s):', end='')
        print(f'\task={ask_time:<5.3f} fit={fit_time:<5.3f} upt_x={upt_x_time:<5.3f} tell={tell_time:<4.3f} ', end='')
        print(f'elite_stat={elite_stat_time:<5.3f}\t', end='')
        print()


    def fit_ada_non_priv(self, key,
                            true_stats,
                            queries,
                            rounds,
                            samples_per_round: int,
                            sync_dataset=None,
                            constraint_fn=None, debug_fn=None):

        if sync_dataset is None:
            sync_dataset = Dataset.synthetic(self.domain, self.data_size, 0)

        selected_stats = jnp.array([], dtype=jnp.int32)
        keys = jax.random.split(key, rounds)
        for T, subkey in enumerate(keys):
            sync_stats = queries.get_all_stats(sync_dataset)
            errors = jnp.abs(true_stats - sync_stats)
            errors = errors.at[selected_stats].set(-jnp.inf)
            print(f'\nT={T}:')
            print(f'Errors: ', errors.max().round(5), errors.mean().round(8))
            debug_fn(-1, 0, sync_dataset)


            select_query_ids = jnp.argsort(-errors)[:samples_per_round]
            select_stats = jnp.concatenate((selected_stats, select_query_ids))

            round_true_stats = true_stats[select_stats]
            round_stat_fn = queries.get_stats_fn(select_stats)

            sync_dataset = self.fit_help(subkey, round_true_stats, round_stat_fn, sync_dataset=sync_dataset, debug_fn=debug_fn)

        return sync_dataset
