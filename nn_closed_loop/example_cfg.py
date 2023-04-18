import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import logging
import jax
logging.getLogger('jax._src.lib.xla_bridge').addFilter(lambda _: False)

import tensorflow as tf
import numpy as np
import torch as th
import nn_closed_loop.dynamics as dynamics
import nn_closed_loop.analyzers as analyzers
import nn_closed_loop.constraints as constraints
from nn_closed_loop.utils.nn import load_controller, load_controller_unity
from nn_closed_loop.utils.utils import (
    range_to_polytope,
    get_polytope_A,
)
import argparse
import ast
import time
from typing import Dict, Tuple
import yaml


dir_path = os.path.dirname(os.path.realpath(__file__))

def main_forward(params: dict) -> Tuple[Dict, Dict]:
    np.random.seed(seed=0)
    stats = {}

    dyn = dynamics.get_dynamics_instance(params["system"]["type"], params["system"]["feedback"])

    controller = load_controller(
        system=dyn.__class__.__name__,
        model_name=params["system"]["controller"]
    )

    # Set up analyzer (+ parititoner + propagator)
    analyzer = analyzers.ClosedLoopAnalyzer(controller, dyn)
    analyzer.partitioner = params["analysis"]["partitioner"]
    analyzer.propagator = params["analysis"]["propagator"]

    initial_state_range = np.array(ast.literal_eval(params["analysis"]["initial_state_range"]))
    initial_state_set = constraints.state_range_to_constraint(initial_state_range, params["analysis"]["propagator"]["boundary_type"])


    if params["analysis"]["estimate_runtime"]:
        # Run the analyzer N times to compute an estimated runtime
        times = np.empty(params["analysis"]["num_calls"])
        final_errors = np.empty(params["analysis"]["num_calls"], dtype=np.ndarray)
        avg_errors = np.empty(params["analysis"]["num_calls"], dtype=np.ndarray)
        all_errors = np.empty(params["analysis"]["num_calls"], dtype=np.ndarray)
        all_reachable_sets = np.empty(params["analysis"]["num_calls"], dtype=object)
        for num in range(params["analysis"]["num_calls"]):
            print('call: {}'.format(num))
            t_start = time.time()
            reachable_sets, analyzer_info = analyzer.get_reachable_set(
                initial_state_set, t_max=params["analysis"]["t_max"]
            )
            t_end = time.time()
            t = t_end - t_start
            times[num] = t

            if num == 0:
                final_error, avg_error, all_error = analyzer.get_error(initial_state_set, reachable_sets, t_max=params["analysis"]["t_max"])
                final_errors[num] = final_error
                avg_errors[num] = avg_error
                all_errors[num] = all_error
                all_reachable_sets[num] = reachable_sets

        stats['runtimes'] = times
        stats['final_step_errors'] = final_errors
        stats['avg_errors'] = avg_errors
        stats['all_errors'] = all_errors
        stats['reachable_sets'] = all_reachable_sets

        print("All times: {}".format(times))
        print("Avg time: {} +/- {}".format(times.mean(), times.std()))
    else:
        # Run analysis once
        t_start = time.time()
        reachable_sets, analyzer_info = analyzer.get_reachable_set(
            initial_state_set, t_max=params["analysis"]["t_max"]
        )
        t_end = time.time()
        print(t_end - t_start)
        stats['reachable_sets'] = reachable_sets

    if params["analysis"]["estimate_error"]:
        final_error, avg_error, errors = analyzer.get_error(initial_state_set, reachable_sets, t_max=params["analysis"]["t_max"])
        print('Final step approximation error: {}'.format(final_error))
        print('Avg errors: {}'.format(avg_error))
        print('All errors: {}'.format(errors))

    if params["visualization"]["save_plot"]:
        save_dir = "{}/results/examples/".format(
            os.path.dirname(os.path.abspath(__file__))
        )
        os.makedirs(save_dir, exist_ok=True)

        # Ugly logic to embed parameters in filename:
        pars = "_".join(
            [
                str(key) + "_" + str(value)
                for key, value in sorted(
                    params["analysis"]["partitioner"].items(), key=lambda kv: kv[0]
                )
                if key
                not in [
                    "make_animation",
                    "show_animation",
                    "type",
                    "num_partitions",
                ]
            ]
        )
        pars2 = "_".join(
            [
                str(key) + "_" + str(value)
                for key, value in sorted(
                    params["analysis"]["propagator"].items(), key=lambda kv: kv[0]
                )
                if key not in ["input_shape", "type"]
            ]
        )
        analyzer_info["save_name"] = (
            save_dir
            + dyn.name
            + pars
            + "_"
            + params["analysis"]["partitioner"]["type"]
            + "_"
            + params["analysis"]["propagator"]["type"]
            + "_"
            + "tmax"
            + "_"
            + str(round(params["analysis"]["t_max"], 1))
            + "_"
            + params["analysis"]["propagator"]["boundary_type"]
        )
        if len(pars2) > 0:
            analyzer_info["save_name"] = (
                analyzer_info["save_name"] + "_" + pars2
            )
        analyzer_info["save_name"] = analyzer_info["save_name"] + ".png"
        
    if params["visualization"]["show_plot"] or params["visualization"]["save_plot"]:
        analyzer.visualize(
            initial_state_set,
            reachable_sets,
            show_samples=params["visualization"]["show_samples"],
            show_trajectories=params["visualization"]["show_trajectories"],
            show=params["visualization"]["show_plot"],
            axis_dims=[[a] for a in params["visualization"]["plot_dims"]],
            axis_labels=params["visualization"]["plot_axis_labels"],
            aspect=params["visualization"]["plot_aspect"],
            plot_lims=params["visualization"]["plot_lims"],
            iteration=None,
            controller_name=None,
            **analyzer_info
        )

    return stats, analyzer_info

def main_backward(args: argparse.Namespace) -> tuple[dict, dict]:
    np.random.seed(seed=0)
    stats = {}

    if params["system"]["feedback"] != "FullState":
        raise ValueError("Currently only support state feedback for backward reachability.")

    dyn = dynamics.get_dynamics_instance(params["system"]["type"], params["system"]["feedback"])

    controller = load_controller(
        system=dyn.__class__.__name__,
        model_name=params["system"]["controller"]
    )

    # Set up analyzer (+ parititoner + propagator)
    analyzer = analyzers.ClosedLoopBackwardAnalyzer(controller, dyn)
    analyzer.partitioner = params["analysis"]["partitioner"]
    analyzer.propagator = params["analysis"]["propagator"]

    final_state_range = np.array(ast.literal_eval(params["analysis"]["final_state_range"]))
    target_set = constraints.state_range_to_constraint(final_state_range, params["analysis"]["propagator"]["boundary_type"])

    if params["analysis"]["estimate_runtime"]:
        # Run the analyzer N times to compute an estimated runtime

        times = np.empty(params["analysis"]["num_calls"])
        final_errors = np.empty(params["analysis"]["num_calls"])
        avg_errors = np.empty(params["analysis"]["num_calls"], dtype=np.ndarray)
        all_errors = np.empty(params["analysis"]["num_calls"], dtype=np.ndarray)
        all_backprojection_sets = np.empty(params["analysis"]["num_calls"], dtype=object)
        target_sets = np.empty(num_calls, dtype=object)
        for num in range(params["analysis"]["num_calls"]):
            print('call: {}'.format(num))
            t_start = time.time()
            backprojection_sets, analyzer_info = analyzer.get_backprojection_set(
                target_set, t_max=params["analysis"]["t_max"], overapprox=params["analysis"]["overapprox"]
            )
            t_end = time.time()
            t = t_end - t_start
            times[num] = t

            if num == 0:
                final_error, avg_error, all_error = analyzer.get_backprojection_error(target_set, backprojection_sets, t_max=params["analysis"]["t_max"])

                final_errors[num] = final_error
                avg_errors[num] = avg_error
                all_errors[num] = all_error
                all_backprojection_sets[num] = backprojection_sets
                target_sets[num] = target_sets



        stats['runtimes'] = times
        stats['final_step_errors'] = final_errors
        stats['avg_errors'] = avg_errors
        stats['all_errors'] = all_errors
        stats['all_backprojection_sets'] = all_backprojection_sets
        stats['target_sets'] = target_sets
        stats['avg_runtime'] = times.mean()

        print("All times: {}".format(times))
        print("Avg time: {} +/- {}".format(times.mean(), times.std()))
        # print('final error: {}'.format(final_error))
        print("Final Error: {}".format(final_errors[-1]))
        print("Avg Error: {}".format(avg_errors[-1]))
    else:
        # Run analysis once
        # Run analysis & generate a plot
        backprojection_sets, analyzer_info = analyzer.get_backprojection_set(
            target_set, t_max=params["analysis"]["t_max"], overapprox=params["analysis"]["overapprox"]
        )
        stats['backprojection_sets'] = backprojection_sets
        
    controller_name=None
    if params["visualization"]["show_policy"]:
        controller_name = params["system"]['controller']

    if params["visualization"]["save_plot"]:
        save_dir = "{}/results/examples_backward/".format(
            os.path.dirname(os.path.abspath(__file__))
        )
        os.makedirs(save_dir, exist_ok=True)

        # Ugly logic to embed parameters in filename:
        pars = "_".join(
            [
                str(key) + "_" + str(value)
                for key, value in sorted(
                    params["analysis"]["partitioner"].items(), key=lambda kv: kv[0]
                )
                if key
                not in [
                    "make_animation",
                    "show_animation",
                    "type",
                    "num_partitions",
                ]
            ]
        )
        pars2 = "_".join(
            [
                str(key) + "_" + str(value)
                for key, value in sorted(
                    params["analysis"]["propagator"].items(), key=lambda kv: kv[0]
                )
                if key not in ["input_shape", "type"]
            ]
        )
        analyzer_info["save_name"] = (
            save_dir
            + params["system"]["type"]
            + pars
            + "_"
            + params["analysis"]["partitioner"]["type"]
            + "_"
            + params["analysis"]["propagator"]["type"]
            + "_"
            # + "tmax"
            # + "_"
            # + str(round(params["analysis"]["t_max"], 1))
            # + "_"
            + params["analysis"]["propagator"]["boundary_type"]
            + "_"
            # + str(params["analysis"]["propagator"]["num_polytope_facets"])
            # + "_"
            + "partitions"
            + "_"
            # + np.array2string(num_partitions, separator='_')[1:-1]
        )
        if len(pars2) > 0:
            analyzer_info["save_name"] = (
                analyzer_info["save_name"] + "_" + pars2
            )
        analyzer_info["save_name"] = analyzer_info["save_name"] + ".png"

    if params["analysis"].get("initial_state_range", None) is None:
        initial_state_set = None
    else:
        initial_state_range = np.array(
            ast.literal_eval(params["analysis"]["initial_state_range"])
        )
        initial_state_set = LpConstraint(initial_state_range)

    if params["visualization"]["show_plot"] or params["visualization"]["save_plot"]:
        analyzer.visualize(
            backprojection_sets,
            target_set,
            analyzer_info,
            show=params["visualization"]["show_plot"],
            show_samples=params["visualization"]["show_samples"],
            show_samples_from_cells=params["visualization"]["show_samples_from_cells"],
            show_trajectories=params["visualization"]["show_trajectories"],
            show_convex_hulls=params["visualization"]["show_convex_hulls"],
            axis_dims=params["visualization"]["plot_dims"],
            axis_labels=params["visualization"]["plot_axis_labels"],
            aspect=params["visualization"]["plot_aspect"],
            plot_lims=params["visualization"]["plot_lims"],
            initial_constraint=initial_state_set,
            controller_name=controller_name,
            show_BReach=params["visualization"]["show_BReach"]
        )

    return stats, analyzer_info


def setup_parser() -> dict:

    parser = argparse.ArgumentParser(
        description="Analyze a closed loop system w/ NN controller."
    )

    parser.add_argument(
        "--config",
        type=str,
        help="file system to analyze (default: double_integrator)",
    )

    args = parser.parse_args()
    with open(f"{args.config}.yaml", mode="r") as file:
        params = yaml.load(file, yaml.Loader)

    return params


if __name__ == "__main__":

    params = setup_parser()

    if params["analysis"]["reachability_direction"] == "forward":
        main_forward(params)
    if params["analysis"]["reachability_direction"] == "backward":
        main_backward(params)
