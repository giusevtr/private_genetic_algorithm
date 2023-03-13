import itertools
import os.path
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
# from dp_data import load_domain_config, load_df
from utils import timer, Dataset, Domain, get_Xy
import numpy as np

# from diffprivlib.models import  LogisticRegression  as PrivLogisticRegression
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from ml_utils import filter_outliers, evaluate_machine_learning_task

from dev.dataloading.data_functions.acs import get_acs_all

if __name__ == "__main__":
    # epsilon_vals = [0.07, 0.1, 0.15, 0.23, 0.52 ,0.74, 1, 2, 5, 10]
    evaluate_original = False
    save_results = True

    epsilon_vals = [0.07, 0.23, 0.52, 0.74, 1, 10]
    seeds = [0, 1, 2]
    Method = 'PrivateGSD'
    # Method = 'RAP'

    dataset_name = 'folktables_2018_multitask_NY'
    data_container_fn = get_acs_all()
    data_container = data_container_fn(seed=0)

    domain = data_container.train.domain
    df_train = data_container.from_dataset_to_df_fn(
        data_container.train
    )
    df_test = data_container.from_dataset_to_df_fn(
        data_container.test
    )

    cat_cols = domain.get_categorical_cols()
    num_cols = domain.get_numeric_cols()
    targets = ['PINCP', 'PUBCOV', 'ESR']
    models = [('LR', lambda: LogisticRegression(max_iter=5000, random_state=0,
                                                solver='liblinear', penalty='l1')),
              # ('RF', lambda: RandomForestClassifier(random_state=0))
              ]

    features = []
    for f in domain.attrs:
        if f not in targets:
            features.append(f)

    Res = []
    for target in ['PINCP', 'PUBCOV']:
        for eps in epsilon_vals:
            for seed in seeds:
                sync_path = ''
                if Method == 'PrivateGSD':
                    sync_path = f'../sync_data/{dataset_name}/PrivateGSD/Ranges/oneshot/{eps:.2f}/sync_data_{seed}.csv'
                    # sync_path = f'../examples/acsmulti/sync_data/{dataset_name}/PrivateGSD/Ranges/oneshot/{eps:.2f}/sync_data_{seed}.csv'
                elif Method == 'RAP':
                    sync_path = f'../sync_data/{dataset_name}/RAP/Ranges/oneshot/{eps:.2f}/sync_data_{seed}.csv'

                if not os.path.exists(sync_path):
                    print(f'Not Found: {sync_path}')
                    continue
                df_sync = pd.read_csv(sync_path, index_col=None)
                data_sync = Dataset(df_sync, domain)
                df_sync_post = data_container.from_dataset_to_df_fn(data_sync)

                for model_name, model in models:
                    clf = model()
                    rep = evaluate_machine_learning_task(df_sync_post, df_test, features, target,
                                                   cat_columns=cat_cols,
                                                   num_columns=num_cols,
                                                   endmodel=clf,
                                                   )
                    f1 = rep['macro avg']['f1-score']
                    acc = rep['accuracy']
                    print(f'{dataset_name}, {Method}+{model_name}, target={target},  eps={eps}:'
                          f'\t acc_test={acc:.3f}, f1_test={f1:.3f}')
                    Res.append([dataset_name, 'Yes', Method, model_name, target, eps, 'F1', seed, f1])
                    Res.append([dataset_name, 'Yes', Method, model_name, target, eps, 'Accuracy', seed, acc])

    results = pd.DataFrame(Res, columns=['Dataset', 'Is DP', 'Method', 'Model', 'Target', 'Epsilon', 'Metric', 'Seed',
                                         'Score'])
    print(results)
    if os.path.exists('results.csv'):
        results_pre = pd.read_csv('results.csv', index_col=None)

        results = results_pre.append(results)
    print(f'Saving results.csv')
    results.to_csv('results.csv', index=False)


