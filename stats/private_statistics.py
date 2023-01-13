# import jax.numpy as jnp
# import jax
# import numpy as np
#
# class PrivateMarginalsState:
#     def __init__(self):
#         self.NUM_STATS = 0
#         self.true_stats = []
#         self.priv_stats = []
#         self.priv_marginals_fn = []
#         self.priv_marginals_fn_jit = []
#         self.priv_diff_marginals_fn = []
#         self.priv_diff_marginals_fn_jit = []
#         self.selected_marginals = []
#
#         self.priv_loss_l2_fn_jit_list = []
#         self.priv_population_l2_loss_fn_list = []
#
#     def add_stats(self, true_stat, priv_stat, marginal_fn, marginal_fn_jit, diff_marginal_fn, diff_marginal_fn_jit):
#         self.NUM_STATS += true_stat.shape[0]
#         self.true_stats.append(true_stat)
#         self.priv_stats.append(priv_stat)
#         self.priv_marginals_fn.append(marginal_fn)
#         self.priv_marginals_fn_jit.append(marginal_fn_jit)
#         self.priv_diff_marginals_fn.append(diff_marginal_fn)
#         self.priv_diff_marginals_fn_jit.append(diff_marginal_fn_jit)
#
#         # priv_loss_fn = lambda X: jnp.linalg.norm(priv_stat - marginal_fn(X), ord=2) / priv_stat.shape[0]
#         priv_loss_fn = lambda X: jnp.linalg.norm(priv_stat - marginal_fn(X), ord=2)
#         priv_loss_fn_jit = jax.jit(priv_loss_fn)
#         self.priv_loss_l2_fn_jit_list.append(priv_loss_fn_jit)
#
#         priv_population_loss_fn_jit_vmap = jax.vmap(priv_loss_fn_jit, in_axes=(0, ))
#         self.priv_population_l2_loss_fn_list.append(jax.jit(priv_population_loss_fn_jit_vmap))
#         # fitness_fn_vmap = lambda x_pop: compute_error_vmap(x_pop)
#         # fitness_fn_vmap_jit = jax.jit(fitness_fn)
#
#         # self.population_stats_fn = jax.vmap(marginal_fn, in_axes=(0,))
#         # self.population_stats_fn_jit = jax.vmap(marginal_fn_jit, in_axes=(0,))
#
#     def get_true_stats(self):
#         return jnp.concatenate(self.true_stats)
#
#     def get_priv_stats(self):
#         return jnp.concatenate(self.priv_stats)
#
#     def priv_stats_fn(self, X):
#         return jnp.concatenate([fn(X) for fn in self.priv_marginals_fn])
#
#     def priv_stats_fn_jit(self, X):
#         return jnp.concatenate([fn(X) for fn in self.priv_marginals_fn_jit])
#
#     def priv_diff_stats_fn(self, X):
#         return jnp.concatenate([diff_fn(X) for diff_fn in self.priv_diff_marginals_fn])
#
#     def priv_diff_stats_fn_jit(self, X):
#         return jnp.concatenate([diff_fn(X) for diff_fn in self.priv_diff_marginals_fn_jit])
#
#     def true_loss_inf(self, X):
#         true_stats_concat = jnp.concatenate(self.true_stats)
#         sync_stats_concat = self.priv_stats_fn_jit(X)
#         return jnp.abs(true_stats_concat - sync_stats_concat).max()
#
#     def true_loss_l2(self, X, use_jit=False):
#         true_stats_concat = jnp.concatenate(self.true_stats)
#         sync_stats_concat = self.priv_stats_fn_jit(X)
#         return jnp.linalg.norm(true_stats_concat - sync_stats_concat, ord=2) / true_stats_concat.shape[0]
#
#     def priv_loss_inf(self, X, use_jit=False):
#         priv_stats_concat = jnp.concatenate(self.priv_stats)
#         sync_stats_concat = self.priv_stats_fn_jit(X)
#         return jnp.abs(priv_stats_concat - sync_stats_concat).max()
#
#     def priv_loss_l2(self, X, use_jit=False):
#         priv_stats_concat = jnp.concatenate(self.priv_stats)
#         sync_stats_concat = self.priv_stats_fn_jit(X)
#         return jnp.linalg.norm(priv_stats_concat - sync_stats_concat, ord=2) / priv_stats_concat.shape[0]
#
#     # def priv_loss_l2_jit(self, X):
#     #     loss = 0
#     #     for jit_fn in self.priv_loss_l2_fn_jit_list:
#     #         loss += jit_fn(X)
#     #     return loss / self.NUM_STATS
#
#
#     # def priv_marginal_loss_l2_jit(self, X):
#     #     losses = []
#     #     # for jit_fn in self.priv_loss_l2_fn_jit_list:
#     #     for i in range(len(self.priv_loss_l2_fn_jit_list)):
#     #         stat_size = self.priv_stats[i].shape[0]
#     #         jit_fn = self.priv_loss_l2_fn_jit_list[i]
#     #         losses.append(jit_fn(X)/stat_size)
#     #     return losses
#
#     def priv_population_l2_loss_fn_jit(self, X_pop):
#         loss = None
#         for jit_fn in self.priv_population_l2_loss_fn_list:
#             this_loss = jit_fn(X_pop)
#             loss = this_loss if loss is None else loss + this_loss
#         # return loss / self.NUM_STATS if loss is not None else 0
#         return loss if loss is not None else 0
#
#
#     def priv_diff_loss_inf(self, X_oh):
#         priv_stats_concat = jnp.concatenate(self.priv_stats)
#         sync_stats_concat = self.priv_diff_stats_fn_jit(X_oh)
#         return jnp.abs(priv_stats_concat - sync_stats_concat).max()
#
#     def priv_diff_loss_l2(self, X_oh):
#         priv_stats_concat = jnp.concatenate(self.priv_stats)
#         sync_stats_concat = self.priv_diff_stats_fn_jit(X_oh)
#         return jnp.linalg.norm(priv_stats_concat - sync_stats_concat, ord=2) ** 2 / priv_stats_concat.shape[0]
#
#
#
