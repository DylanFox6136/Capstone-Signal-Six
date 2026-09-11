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
daily_loss = 0.0028
# Panel Power Output
area_m2 = 2.69
efficiency = 0.192
panel_transmittance = (1.0 - daily_loss) ** time_steps
power_output_watts = surface_irradiance * area_m2 * efficiency * panel_transmittance
target_max_power = 50.0
current_max_power = np.max(power_output_watts)
power_output_watts *= (target_max_power / current_max_power)
# Plotting the results over the Martian year
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# Power Output Subplot
ax1.plot(time_steps, power_output_watts, color='#e67e22', linewidth=0.8, alpha=0.8)
ax1.set_ylabel('Power Output (W)', fontsize=11)
ax1.set_title('Martian Solar Panel Simulation (1 Martian Year / 668.6 Sols)', fontsize=13, fontweight='bold')
ax1.grid(True, linestyle='--', alpha=0.5)

# Dust Accumulation Subplot
ax2.plot(time_steps, panel_transmittance * 100, color='#7f8c8d', linewidth=1.0)
ax2.set_ylabel('Operating efficiency (%)', fontsize=11)
ax2.set_xlabel('Time (Sols)', fontsize=11)
ax2.grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.savefig('mars_solar_simulation.png', dpi=300)
plt.show()
