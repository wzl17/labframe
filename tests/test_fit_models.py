import unittest

import numpy as np
from lmfit import Model

from fit_models import (
    exponential_model,
    gaussian_model,
    linear_model,
    power_law_model,
    sine_model,
)


class FitModelsTest(unittest.TestCase):
    def test_exports_are_lmfit_models(self) -> None:
        for model in (
            sine_model,
            linear_model,
            gaussian_model,
            exponential_model,
            power_law_model,
        ):
            with self.subTest(model=model.name):
                self.assertIsInstance(model, Model)

    def test_sine_guess_converges_to_clean_signal(self) -> None:
        x_values = np.linspace(0.0, 2.0, 401)
        y_values = 0.4 + 1.7 * np.sin(2.0 * np.pi * 2.5 * x_values - 0.3)

        parameters = sine_model.guess(y_values, x=x_values)
        result = sine_model.fit(y_values, parameters, x=x_values)

        self.assertTrue(result.success)
        self.assertAlmostEqual(result.params["amplitude"].value, 1.7, places=5)
        self.assertAlmostEqual(result.params["frequency"].value, 2.5, places=5)
        self.assertAlmostEqual(result.params["offset"].value, 0.4, places=5)


if __name__ == "__main__":
    unittest.main()
