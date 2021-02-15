import numpy as np
import matplotlib.pyplot as plt
# from matplotlib.patches import Rectangle
from partition.utils.utils import get_sampled_outputs, samples_to_range

plt.rcParams['mathtext.fontset'] = 'stix'
plt.rcParams['font.family'] = 'STIXGeneral'
plt.rcParams['font.size'] = '20'

import partition.partitioners as partitioners
import partition.propagators as propagators

class Analyzer:
    def __init__(self, torch_model):
        self.torch_model = torch_model

        self.partitioner = None
        self.propagator = None

    @property
    def partitioner(self):
        return self._partitioner

    @partitioner.setter
    def partitioner(self, hyperparams):
        if hyperparams is None: return
        hyperparams_ = hyperparams.copy()
        partitioner = hyperparams_.pop('type', None)
        self._partitioner = partitioners.partitioner_dict[partitioner](**hyperparams_)

    @property
    def propagator(self):
        return self._propagator

    @propagator.setter
    def propagator(self, hyperparams):
        if hyperparams is None: return
        hyperparams_ = hyperparams.copy()
        propagator = hyperparams_.pop('type', None)
        self._propagator = propagators.propagator_dict[propagator](**hyperparams_)
        if propagator is not None:
            self._propagator.network = self.torch_model

    def get_output_range(self, input_range, verbose=False):
        output_range, info = self.partitioner.get_output_range(input_range, self.propagator)
        return output_range, info

    def visualize(self, input_range, output_range_estimate, show=True, show_samples=True, show_legend=True, show_input=True, show_output=True, title=None, labels={}, aspects={}, **kwargs):
        # sampled_outputs = self.get_sampled_outputs(input_range)
        # output_range_exact = self.samples_to_range(sampled_outputs)

        self.partitioner.setup_visualization(input_range, output_range_estimate, self.propagator, show_samples=show_samples, inputs_to_highlight=kwargs.get('inputs_to_highlight', None), outputs_to_highlight=kwargs.get('outputs_to_highlight', None),
            show_input=show_input, show_output=show_output, labels=labels, aspects=aspects)
        self.partitioner.visualize(kwargs.get("exterior_partitions", kwargs.get("all_partitions", [])), kwargs.get("interior_partitions", []), output_range_estimate,
            show_input=show_input, show_output=show_output)

        if show_legend:
            if show_input:
                self.partitioner.input_axis.legend(bbox_to_anchor=(0,1.02,1,0.2), loc="lower left",
                        mode="expand", borderaxespad=0, ncol=1)
            if show_output:
                self.partitioner.output_axis.legend(bbox_to_anchor=(0,1.02,1,0.2), loc="lower left",
                        mode="expand", borderaxespad=0, ncol=2)

        if title is not None:
            plt.title(title)

        plt.tight_layout()

        if "save_name" in kwargs and kwargs["save_name"] is not None:
            plt.savefig(kwargs["save_name"])

        if show:
            plt.show()
        else:
            plt.close()

    def get_sampled_outputs(self, input_range, N=1000):
        return get_sampled_outputs(input_range, self.propagator, N=N)

    def samples_to_range(self, sampled_outputs):
        return samples_to_range(sampled_outputs)

    def get_exact_output_range(self, input_range):
        sampled_outputs = self.get_sampled_outputs(input_range)
        output_range = self.samples_to_range(sampled_outputs)
        return output_range

    def get_exact_hull(self, input_range, N=int(1e7)):
        from scipy.spatial import ConvexHull
        sampled_outputs = self.get_sampled_outputs(input_range, N=N)
        return ConvexHull(sampled_outputs)
