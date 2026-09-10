import numpy as np
import matplotlib.pyplot as plt

# Constants
SOLS_PER_YEAR = 668.6
HOURS_PER_SOL = 24.0
total_hours = int(SOLS_PER_YEAR * HOURS_PER_SOL)
time_steps = np.linspace(0, SOLS_PER_YEAR, total_hours)

# Orbital mechanics & Atmospheric Dust (Tau)
ls = (360.0 * (time_steps / SOLS_PER_YEAR)) % 360.0
ls_rad = np.radians(ls)
atmospheric_tau = 0.6 + 2.0 * np.exp(-((ls - 250.0) / 30.0)**2)

# Solar geometry (simplified average tilt)
cos_zenith = np.maximum(0.0, np.cos(np.radians(45.0) - 0.2 * np.sin(ls_rad)))
surface_irradiance = 590.0 * np.exp(-atmospheric_tau / (cos_zenith + 1e-5)) * cos_zenith

# Dust Accumulation Modeling
dust_loss = np.zeros(total_hours)
deposition_rate_per_hour = 0.00015
wind_cleaning_probability = 0.005

current_dust = 0.0
np.random.seed(42)

for i in range(1, total_hours):
    storm_multiplier = 1.0 + (atmospheric_tau[i] / 1.0)
    current_dust += deposition_rate_per_hour * storm_multiplier
    
    if np.random.rand() < wind_cleaning_probability:
        clearing_efficiency = np.random.uniform(0.5, 1.0)
        current_dust *= (1.0 - clearing_efficiency)
        
    current_dust = min(current_dust, 0.85)
    dust_loss[i] = current_dust

# Panel Power Output
area_m2 = 1.0
efficiency = 0.20
panel_transmittance = 1.0 - dust_loss
power_output_watts = surface_irradiance * area_m2 * efficiency * panel_transmittance

# Plotting the results over the Martian year
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# Power Output Subplot
ax1.plot(time_steps, power_output_watts, color='#e67e22', linewidth=0.8, alpha=0.8)
ax1.set_ylabel('Power Output (W)', fontsize=11)
ax1.set_title('Martian Solar Panel Simulation (1 Martian Year / 668.6 Sols)', fontsize=13, fontweight='bold')
ax1.grid(True, linestyle='--', alpha=0.5)

# Dust Accumulation Subplot
ax2.plot(time_steps, dust_loss * 100, color='#7f8c8d', linewidth=1.0)
ax2.set_ylabel('Panel Dust Blockage (%)', fontsize=11)
ax2.set_xlabel('Time (Sols)', fontsize=11)
ax2.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig('mars_solar_simulation.png', dpi=300)
plt.show()

