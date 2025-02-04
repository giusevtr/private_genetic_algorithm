import itertools
import os.path
import pickle
import seaborn as sns

import jax.random
import matplotlib.pyplot as plt
import pandas as pd

from models import GSD
from stats import ChainedStatistics, Halfspace, Marginals
# from utils.utils_data import get_data
import jax.numpy as jnp
# from dp_data.data import get_data
from dp_data import load_domain_config, load_df, DataPreprocessor, ml_eval
from utils import timer, Dataset, Domain
from utils.cdp2adp import cdp_rho, cdp_eps
import numpy as np


if __name__ == "__main__":
    dataset_name = 'folktables_2018_multitask_CA'
    root_path = '../../../dp-data-dev/datasets/preprocessed/folktables/1-Year/'
    config = load_domain_config(dataset_name, root_path=root_path)
    df_train = load_df(dataset_name, root_path=root_path, idxs_path='seed0/train')
    df_test = load_df(dataset_name, root_path=root_path, idxs_path='seed0/test')

    preprocesor: DataPreprocessor
    preprocesor = pickle.load(open(f'{root_path}/{dataset_name}/preprocessor.pkl', 'rb'))


    print(f'train size: {df_train.shape}')
    print(f'test size:  {df_test.shape}')

    domain = Domain.fromdict(config)
    cat_cols = domain.get_categorical_cols()
    num_cols = domain.get_numeric_cols()
    targets = ['JWMNP_bin', 'PINCP', 'ESR', 'MIG', 'PUBCOV']
    features = []
    for f in domain.attrs:
        if f not in targets:
            features.append(f)
    model = 'LogisticRegression'
    q_short_name = 'HS'
    ml_fn = ml_eval.get_evaluate_ml(df_test, config, targets, models=[model])

    # data = Dataset(df_train, domain)
    # # Debug marginals
    # module0 = Marginals.get_kway_categorical(domain, k=2)
    # stat_module = ChainedStatistics([module0])
    # stat_module.fit(data)
    # true_stats = stat_module.get_all_true_statistics()
    # stat_fn = stat_module.get_dataset_statistics_fn()
    # hs = Halfspace(domain=domain,
    #                                      k_cat=1,
    #              cat_kway_combinations=[(c,) for c in targets],
    #              rng=jax.random.key(0),
    #              num_random_halfspaces=200000)
    # hs_stat_fn = hs._get_dataset_statistics_fn()
    # hs_true_stats = hs_stat_fn(data)

    T = [100]
    S = [5]
    # epsilon_vals = [1, 0.74, 0.52, 0.23, 0.07]
    epsilon_vals = [1]
    seeds = [0]

    Res = []
    for eps, seed, t, s in itertools.product(epsilon_vals, seeds, T, S):

        sync_path = f'sync_data/RAP++/folktables_2018_multitask_CA/{eps:.2f}/({s}, {t})/{seed}/synthetic.csv'
        if not os.path.exists(sync_path):
            print(f'{sync_path} NOT FOUND')
            continue

        print(f'reading {sync_path}')
        df_sync_post = pd.read_csv(sync_path)

<<<<<<< HEAD
=======
        # sync_dataset = Dataset(df_sync_post, domain)
        # errors = np.abs(true_stats - stat_fn(sync_dataset))
        # hs_errors = np.abs(hs_true_stats - hs_stat_fn(sync_dataset))
        # print(f'Marginal max error ={errors.max()}, mean error ={errors.mean()}')
        # print(f'HS max error ={hs_errors.max()}, mean error ={hs_errors.mean()}')

>>>>>>> 5959434720650aeb3e5867105da945038e42f97c
        res = ml_fn(df_sync_post, seed=0)
        res = res[res['Eval Data'] == 'Test']
        # res = res[res['Metric'] == 'f1_macro']
        print('seed=', seed, 'eps=', eps)
        print(res)
        for i, row in res.iterrows():
            target = row['target']
<<<<<<< HEAD
            f1 = row['Score']
            metric = row['Metric']
            score = row['Score']
            Res.append([dataset_name, 'Yes', f'RAP++', q_short_name, t, s, model, target, eps, metric, seed, score])

    results = pd.DataFrame(Res, columns=['Data', 'Is DP',
                                         'Generator',
                                         'Statistics',
=======
            score = row['Score']
            metric = row['Metric']
            Res.append([dataset_name, 'Yes', 'RAP++', '2Cat+HS', t, s, 'LR', target, eps, metric, seed, score])
            # Res.append([dataset_name, 'Yes', algo_name+query_name, 'LR', target, eps, 'Accuracy', seed, acc])

            print(f'target={target:<5}, metric={metric:<5}, score={score:.5f}')

    results = pd.DataFrame(Res, columns=['Data', 'Is DP', 'Generator',
>>>>>>> 5959434720650aeb3e5867105da945038e42f97c
                                         'T', 'S',
                                         'Model',
                                         'Target', 'epsilon', 'Metric',
                                         'seed',
                                         'Score'])

    print(results)
    file_path = 'results_final'
    os.makedirs(file_path, exist_ok=True)
    file_path = f'results_final/results_rap++_{model}.csv'
    # if os.path.exists(file_path):
    #     results_pre = pd.read_csv(file_path, index_col=None)
    #     results = results_pre.append(results)
    print(f'Saving ', file_path)
    results.to_csv(file_path, index=False)