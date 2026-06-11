import pandas as pd

df = pd.read_csv('data_cache/frame_stats.csv')

# Frames with n_l2 == 0
zero_l2 = df[df['n_l2'] == 0]
print(f"Frames with n_l2=0: {len(zero_l2)}")
print(f"Their n_objects range: {zero_l2['n_objects'].min()} - {zero_l2['n_objects'].max()}")
print(f"Their generated: min={zero_l2['generated'].min()}, max={zero_l2['generated'].max()}")
print(f"Their init_rate_l2 unique values: {zero_l2['init_rate_l2'].unique()}")
print()

# Current: init_rate_l2 = init_l2/n_l2, when n_l2=0 returns 0
# Correct: if n_l2=0, coverage should be 1.0 (nothing to cover = fully covered)
print("Current: n_l2=0 -> init_rate_l2=0 (wrong)")
print("Correct: n_l2=0 -> init_rate_l2=1.0 (nothing to cover)")
print()

# Fix and compare
df_fixed = df.copy()
df_fixed.loc[df_fixed['n_l2'] == 0, 'init_rate_l2'] = 1.0
df_fixed.loc[df_fixed['n_l2'] == 0, 'init_rate_l1'] = 1.0
df_fixed.loc[df_fixed['n_l2'] == 0, 'init_rate_l0'] = 1.0

print(f"Before fix: mean init_rate_l2 = {df['init_rate_l2'].mean()*100:.2f}%")
print(f"After fix:  mean init_rate_l2 = {df_fixed['init_rate_l2'].mean()*100:.2f}%")
print()

# By group (fixed)
for g in ['S','M','L']:
    gdf = df_fixed[df_fixed['size_group']==g]
    l0 = gdf['init_rate_l0'].mean()*100
    l1 = gdf['init_rate_l1'].mean()*100
    l2 = gdf['init_rate_l2'].mean()*100
    print(f"Group {g} (fixed): L0={l0:.1f}%, L1={l1:.1f}%, L2={l2:.1f}%")

print()
# Compare with R1: S=56.3/7.9/1.8, M=40.5/1.8/0.3, L=32.8/0.8/0.1
print("R1 reference: S=56.3/7.9/1.8, M=40.5/1.8/0.3, L=32.8/0.8/0.1")
print()

# How many of the 244 extra frames are in each group?
print("Extra 244 frames (n_l2=0) by size_group:")
print(zero_l2['size_group'].value_counts())
print()

# If we exclude n_l2=0 frames (like R1 did), what do we get?
df_excl = df[df['n_l2'] > 0]
print(f"Excluding n_l2=0 frames ({len(df_excl)} remaining):")
for g in ['S','M','L']:
    gdf = df_excl[df_excl['size_group']==g]
    l0 = gdf['init_rate_l0'].mean()*100
    l1 = gdf['init_rate_l1'].mean()*100
    l2 = gdf['init_rate_l2'].mean()*100
    print(f"  Group {g}: L0={l0:.1f}%, L1={l1:.1f}%, L2={l2:.1f}%  (N={len(gdf)})")
