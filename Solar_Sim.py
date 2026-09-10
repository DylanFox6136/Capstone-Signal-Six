import numpy as np 

#General mars data
SOLs_Per_Year = 668.6
Hours_per_SOL = 24.66

#total hrs per year
Total_Hours_Per_Year = SOLs_Per_Year * Hours_per_SOL
time_steps = np.linspace(0, SOLs_Per_Year, Total_Hours_Per_Year)

# Simplified Mars orbital approximation (Solar Longitude Ls from 0 to 360 degrees)
ls = (360.0 * (time_steps / SOLS_PER_YEAR)) % 360.0
ls_rad = np.radians(ls)

# Atmospheric optical depth (base dust + seasonal storm spike around Ls = 250)
tau = 0.6 + 2.0 * np.exp(-((ls - 250.0) / 30.0)**2)

# Direct solar irradiance on the surface using Beer-Lambert attenuation
cos_zenith_avg = np.maximum(0.0, np.cos(np.radians(45.0) - 0.2 * np.sin(ls_rad)))
surface_irradiance = solar_constant_mars * np.exp(-tau / (cos_zenith_avg + 1e-5)) * cos_zenith_avg

# Panel characteristics
area_m2 = 1.0
efficiency = 0.20  # 20% efficient photovoltaic panel
power_output_watts = surface_irradiance * area_m2 * efficiency

print(f"Max power output: {np.max(power_output_watts):.2f} W")
print(f"Min power output: {np.min(power_output_watts):.
