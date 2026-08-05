"""Reusable lmfit model objects."""

from lmfit.models import ConstantModel, ExponentialModel, GaussianModel, LinearModel, PowerLawModel, SineModel

sine_offset_model = SineModel() + ConstantModel()
linear_model = LinearModel()
gaussian_model = GaussianModel()
exponential_model = ExponentialModel()
power_law_model = PowerLawModel()
