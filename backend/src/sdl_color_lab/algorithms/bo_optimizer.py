"""BO-EI decisions with a seeded first trial when no observations are available."""

import numpy as np
import torch
from botorch.acquisition import LogExpectedImprovement
from botorch.fit import fit_gpytorch_mll
from botorch.models import SingleTaskGP
from botorch.optim import optimize_acqf
from gpytorch.mlls import ExactMarginalLogLikelihood

from sdl_color_lab.core.common import NAMES, TOTAL, delta_e


def suggest(state: dict, calibration: list[dict]) -> dict:
    """Propose one 200 µL recipe; the first exploration counts towards the budget."""
    history = state.get("history", [])
    if len(history) >= state.get("budget", 12):
        raise ValueError("The experiment budget is exhausted.")
    if state.get("initialization_mode") == "cold_start" and calibration:
        raise ValueError("Cold-start BO cannot receive measured base colours")
    observations = [*calibration, *history]
    if not observations:
        # No GP can be fitted yet. Sample the simplex once, reproducibly, without
        # using reagent colours, target-derived heuristics or simulator spectra.
        seed = state.get("seed", 0)
        volumes = np.round(
            np.random.default_rng(seed).dirichlet(np.ones(len(NAMES))) * TOTAL
        ).astype(int)
        volumes[int(np.argmax(volumes))] += TOTAL - int(volumes.sum())
        return {
            "reasoning": f"Seeded exploration (seed={seed}); first trial, no observations",
            "recipe": {name: int(value) for name, value in zip(NAMES, volumes)},
        }
    train_x = torch.tensor(
        [[row["recipe"][name] / TOTAL for name in NAMES] for row in observations],
        dtype=torch.double,
    )
    train_y = torch.tensor(
        [[-delta_e(row["rgb"], state["target_rgb"])] for row in observations],
        dtype=torch.double,
    )
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(state.get("seed", 0))
        model = SingleTaskGP(train_x, train_y)
        fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
        acquisition = LogExpectedImprovement(model, best_f=train_y.max() + 0.01)
        candidates, _ = optimize_acqf(
            acquisition,
            bounds=torch.tensor([[0.0] * 4, [1.0] * 4], dtype=torch.double),
            q=1,
            num_restarts=10,
            raw_samples=64,
            equality_constraints=[
                (torch.arange(4), torch.ones(4, dtype=torch.double), 1.0)
            ],
        )
    # Original colour adapter: rescale, round, and absorb error in largest volume.
    volumes = np.clip(candidates[0].detach().numpy() * TOTAL, 0, None)
    volumes = (
        volumes / volumes.sum() * TOTAL
        if volumes.sum() > 0
        else np.array([float(TOTAL), 0.0, 0.0, 0.0])
    )
    volumes = np.round(volumes).astype(int)
    volumes[int(np.argmax(volumes))] += TOTAL - int(volumes.sum())
    return {
        "reasoning": "Bayesian Optimization (EI)",
        "recipe": {name: int(value) for name, value in zip(NAMES, volumes)},
    }
