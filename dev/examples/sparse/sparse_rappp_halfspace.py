import itertools
import jax
# from models import Generator, RelaxedProjectionPP
from models import RelaxedProjectionPPneurips as RelaxedProjectionPP
from stats import HalfspaceDiff, PrefixDiff, ChainedStatistics
from dev.toy_datasets.sparse import get_sparse_dataset
import time
from plot import plot_sparse


PRINT_PROGRESS = True
ROUNDS = 10
SAMPLES = 10
EPSILON = [10]
# EPSILON = [1]
SEEDS = [0]


if __name__ == "__main__":

    data = get_sparse_dataset(DATA_SIZE=10000)
    key_hs = jax.random.PRNGKey(0)
    module = HalfspaceDiff.get_kway_random_halfspaces(data.domain, k=1, rng=key_hs,
                                                                           random_hs=1000)

    stats_module = ChainedStatistics([module,
                                     # module1
                                     ])
    stats_module.fit(data)

    true_stats = stats_module.get_all_true_statistics()
    stat_fn = stats_module.get_dataset_statistics_fn()

    data_size = 500
    rappp = RelaxedProjectionPP(
        domain=data.domain,
        data_size=data_size,
        learning_rate=(0.005,),
        print_progress=True,
        )

    RESULTS = []
    for eps, seed in itertools.product(EPSILON, SEEDS):

        def debug_fn(t, tempdata):
            plot_sparse(tempdata.to_numpy(), title=f'epoch={t}, RAP++, Halfspace, eps={eps:.2f}',
                    alpha=0.9, s=0.8)

        print(f'Starting {rappp}:')
        stime = time.time()
        key = jax.random.PRNGKey(seed)

        sync_data = rappp.fit_dp_adaptive(key, stat_module=stats_module,  epsilon=eps, delta=1e-6,
                                            rounds=ROUNDS, num_sample=SAMPLES, print_progress=True, debug_fn=debug_fn)
        plot_sparse(sync_data.to_numpy(), title=f'RAP++, Prefix, eps={eps:.2f}', alpha=0.9, s=0.8)

        errors = jax.numpy.abs(true_stats - stat_fn(sync_data))
        ave_error = jax.numpy.linalg.norm(errors, ord=1)
        print(f'{str(rappp)}: max error = {errors.max():.4f}, ave_error={ave_error:.6f}, time={time.time()-stime:.4f}')